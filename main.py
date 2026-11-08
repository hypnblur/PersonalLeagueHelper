import argparse
import os
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LCU_POLL_INTERVAL, OPEN_BROWSER, RUNE_PAGE_PREFIX, SAFE_RUNE_IMPORT, WEB_HOST, WEB_PORT
from src.data.companion_db import CompanionDB
from src.data.dragon import DataDragon
from src.data.store import ChampionStore
from src.engine.draft import DraftAdvisor
from src.engine.intel import PlayerIntelService
from src.engine.postgame import PostGameAnalyzer
from src.engine.recommender import Recommender
from src.lcu.connector import LCUConnector
from src.web.server import WebServer


class AppState:
    def __init__(self, dragon, store, lcu, recommender, postgame, db, intel=None, draft=None):
        self.dragon = dragon
        self.store = store
        self.lcu = lcu
        self.recommender = recommender
        self.postgame = postgame
        self.db = db
        self.intel = intel
        self.draft = draft
        self._lock = threading.RLock()
        self._champ_select = None
        self._phase = "None"
        self._my_role = ""
        self._owned_names = set()
        self._owned_at = 0
        self._mastery = {}
        self._mastery_at = 0
        self._draft_ai = {"status": "idle", "text": ""}

    def _set(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self):
        with self._lock:
            champ_select = self._champ_select
            phase = self._phase
            my_role = self._my_role
            owned_count = len(self._owned_names)
        state = {
            "lcu_connected": self.lcu.connected,
            "phase": phase,
            "my_role": my_role,
            "owned_champions": owned_count,
            "summoner": None,
            "patch": self.dragon.version,
            "champ_select": None,
            "recommendations": [],
            "player_intel": self.intel.snapshot() if self.intel else [],
            "recap_available": self.postgame.latest_recap is not None,
            "recap_analyzing": self.postgame.analyzing,
            "recap_has_key": self.postgame.has_key,
            "safe_rune_import": SAFE_RUNE_IMPORT,
        }

        if self.lcu.connected and self.lcu.summoner:
            s = self.lcu.summoner
            state["summoner"] = {
                "name": s.get("gameName", s.get("displayName", "Summoner")),
                "tag": s.get("tagLine", ""),
                "level": s.get("summonerLevel", 0),
            }

        if champ_select:
            cs = self._parse_champ_select(champ_select)
            state["champ_select"] = cs
            allies = [p["champion"] for p in cs["my_team"] if p["champion"] and not p["is_me"]]
            enemies = [p["champion"] for p in cs["enemy_team"] if p["champion"]]
            role = cs.get("my_position", "") or my_role
            if role:
                state["recommendations"] = self.recommend(role, allies, enemies)

        return state

    def _parse_champ_select(self, session):
        my_team, enemy_team = [], []
        local_cell = session.get("localPlayerCellId", -1)
        my_pos = ""

        for m in session.get("myTeam", []):
            cid = m.get("championId", 0) or m.get("championPickIntent", 0)
            is_me = m.get("cellId") == local_cell
            pos = m.get("assignedPosition", "")
            if is_me:
                my_pos = pos
            s1, s2 = m.get("spell1Id") or 0, m.get("spell2Id") or 0
            my_team.append({
                "champion": self.dragon.champion_name(cid) if cid else "",
                "champion_id": cid,
                "position": pos,
                "is_me": is_me,
                "icon": self.dragon.champion_icon(cid) if cid else "",
                "summoner_id": m.get("summonerId") or 0,
                "puuid": m.get("puuid") or "",
                "name": m.get("name") or m.get("summonerName") or "",
                "team": "ally",
                "spell1_id": s1,
                "spell2_id": s2,
                "spells": self.dragon.resolve_summoner_spells(s1, s2),
            })

        for m in session.get("theirTeam", []):
            cid = m.get("championId", 0) or m.get("championPickIntent", 0)
            s1, s2 = m.get("spell1Id") or 0, m.get("spell2Id") or 0
            enemy_team.append({
                "champion": self.dragon.champion_name(cid) if cid else "",
                "champion_id": cid,
                "position": m.get("assignedPosition", ""),
                "icon": self.dragon.champion_icon(cid) if cid else "",
                "summoner_id": m.get("summonerId") or 0,
                "puuid": m.get("puuid") or "",
                "name": m.get("name") or m.get("summonerName") or "",
                "team": "enemy",
                "spell1_id": s1,
                "spell2_id": s2,
                "spells": self.dragon.resolve_summoner_spells(s1, s2),
            })

        return {"my_team": my_team, "enemy_team": enemy_team, "my_position": my_pos}

    def _participants_from_champ_select(self, session):
        cs = self._parse_champ_select(session)
        players = []
        for p in cs.get("my_team", []) + cs.get("enemy_team", []):
            if p.get("puuid") or p.get("summoner_id") or p.get("name") or p.get("champion_id"):
                players.append(p)
        return players

    def _spell_ids_from(self, obj):
        if not isinstance(obj, dict):
            return 0, 0
        s1 = obj.get("spell1Id") or obj.get("summonerSpell1Id") or obj.get("summoner1Id") or 0
        s2 = obj.get("spell2Id") or obj.get("summonerSpell2Id") or obj.get("summoner2Id") or 0
        try:
            return int(s1 or 0), int(s2 or 0)
        except Exception:
            return 0, 0

    def _participants_from_gameflow(self, gameflow):
        if not isinstance(gameflow, dict):
            return []
        game_data = gameflow.get("gameData") or {}
        # Build participant index from team arrays when available
        by_key = {}
        me_puuid = ((self.lcu.summoner or {}).get("puuid")) if self.lcu else None
        for team_name in ("teamOne", "teamTwo"):
            for m in game_data.get(team_name) or []:
                if not isinstance(m, dict):
                    continue
                puuid = m.get("puuid") or ""
                sid = m.get("summonerId") or 0
                key = puuid or (f"sid:{sid}" if sid else None) or m.get("summonerName") or m.get("summonerInternalName")
                if not key:
                    continue
                s1, s2 = self._spell_ids_from(m)
                by_key[key] = {
                    "puuid": puuid,
                    "summoner_id": sid,
                    "name": m.get("summonerName") or m.get("summonerInternalName") or "",
                    "champion_id": m.get("championId") or 0,
                    "champion": self.dragon.champion_name(m.get("championId")) if m.get("championId") else "",
                    "team": "ally" if team_name == "teamOne" else "enemy",  # best-effort; corrected below if possible
                    "is_me": bool(me_puuid and puuid and puuid == me_puuid),
                    "party_id": m.get("partyId") or m.get("teamParticipantId") or "",
                    "spell1_id": s1,
                    "spell2_id": s2,
                    "spells": self.dragon.resolve_summoner_spells(s1, s2),
                }
        # playerChampionSelections often has better champion/spell mapping
        for sel in game_data.get("playerChampionSelections") or []:
            if not isinstance(sel, dict):
                continue
            puuid = sel.get("puuid") or ""
            sid = sel.get("summonerInternalName") or ""  # not always present; best-effort
            s1, s2 = self._spell_ids_from(sel)
            # try match by puuid
            for k, p in by_key.items():
                if puuid and p.get("puuid") == puuid:
                    cid = sel.get("championId") or p.get("champion_id")
                    p["champion_id"] = cid
                    p["champion"] = self.dragon.champion_name(cid) if cid else p.get("champion", "")
                    if s1 or s2:
                        p["spell1_id"], p["spell2_id"] = s1, s2
                        p["spells"] = self.dragon.resolve_summoner_spells(s1, s2)
        # Try to correct ally/enemy using local player's team if present
        my_team_key = None
        for k, p in by_key.items():
            if p.get("is_me"):
                my_team_key = p.get("team")
                break
        if my_team_key == "enemy":
            # flip if we guessed wrong
            for p in by_key.values():
                p["team"] = "ally" if p.get("team") == "enemy" else "enemy"
                p["is_me"] = bool(me_puuid and p.get("puuid") and p.get("puuid") == me_puuid)
        return list(by_key.values())

    def _annotate_parties(self, participants, lobby=None):
        """Best-effort premade/party hints. Enemies are usually hidden by the client."""
        participants = [dict(p) for p in (participants or [])]
        lobby_members = []
        if isinstance(lobby, dict):
            lobby_members = lobby.get("members") or []
            if not lobby_members and isinstance(lobby.get("localMember"), dict):
                lobby_members = [lobby.get("localMember")]
        lobby_ids = set()
        for m in lobby_members:
            if not isinstance(m, dict):
                continue
            if m.get("puuid"):
                lobby_ids.add(("puuid", m.get("puuid")))
            if m.get("summonerId"):
                lobby_ids.add(("sid", int(m.get("summonerId") or 0)))
        lobby_party = len(lobby_members) > 1

        # explicit partyId grouping if present
        groups = {}
        for p in participants:
            pid = p.get("party_id") or p.get("partyId")
            if pid:
                groups.setdefault(str(pid), []).append(p)

        for p in participants:
            is_me = bool(p.get("is_me"))
            in_lobby_party = (("puuid", p.get("puuid")) in lobby_ids) or (("sid", int(p.get("summoner_id") or 0)) in lobby_ids)
            pid = p.get("party_id") or p.get("partyId")
            if pid and len(groups.get(str(pid), [])) > 1:
                p["party"] = {"status": "premade", "label": f"Premade ({len(groups[str(pid)])})", "detail": "Detected from game data"}
            elif in_lobby_party and lobby_party:
                p["party"] = {"status": "premade", "label": f"Your party ({len(lobby_members)})", "detail": "Detected from lobby"}
            elif in_lobby_party and not lobby_party and is_me:
                p["party"] = {"status": "solo", "label": "Solo (lobby)", "detail": "No lobby party members detected"}
            elif p.get("team") == "enemy":
                p["party"] = {"status": "hidden", "label": "Hidden/unknown", "detail": "Enemy premade status is usually not exposed"}
            elif is_me:
                p["party"] = {"status": "unknown", "label": "Unknown", "detail": "Not enough info exposed"}
            else:
                p["party"] = {"status": "unknown", "label": "Unknown", "detail": "Best-effort; client may not expose ally premade status"}
        return participants

    def build_info(self, champion, role=None, enemies=None):
        champ = self.store.get(champion)
        if not champ:
            return {"error": f"No data for '{champion}'"}
        if not role:
            role = (champ.get("roles") or ["mid"])[0]
        options = self.store.get_build_options(champion, role, limit=3)
        if not options:
            return {"error": f"No build for {champion} {role}"}
        if enemies and self.draft:
            adaptive = self.draft.adaptive_build(self.store, champion, role, enemies=enemies)
            if adaptive:
                options = list(options) + [adaptive]
        return {
            "champion": champion,
            "role": role,
            "tier": champ.get("tier", {}).get(role, "?"),
            "build": options[0],  # compatibility
            "build_options": options,
        }

    def refresh_ownership(self, force=False):
        if not self.lcu.connected:
            return
        now = time.time()
        with self._lock:
            if not force and self._owned_names and (now - self._owned_at) < 600:
                return
        try:
            owned = self.lcu.get_owned_champions() or []
            names = set()
            for c in owned:
                if not isinstance(c, dict):
                    continue
                # common shapes: {id, name, ownership:{owned}}, or {championId}, or pickable ids
                is_owned = True
                ownership = c.get("ownership")
                if isinstance(ownership, dict) and ownership.get("owned") is False:
                    is_owned = False
                if c.get("owned") is False:
                    is_owned = False
                if not is_owned:
                    continue
                name = c.get("name") or c.get("alias")
                cid = c.get("id") or c.get("championId")
                if not name and cid:
                    name = self.dragon.champion_name(cid)
                if name and name != "Unknown" and not str(name).startswith("Champion "):
                    names.add(name)
            if names:
                with self._lock:
                    self._owned_names = names
                    self._owned_at = now
        except Exception:
            pass

    def recommend(self, role, allies, enemies):
        with self._lock:
            owned = set(self._owned_names)
        personal = {}
        try:
            personal = self.db.champion_personal_stats() if self.db else {}
        except Exception:
            pass
        return self.recommender.recommend(role, allies, enemies, owned=owned or None, personal=personal)

    def refresh_mastery(self, force=False):
        if not self.lcu.connected or not (self.lcu.summoner or {}).get("puuid"):
            return
        now = time.time()
        with self._lock:
            if not force and self._mastery and (now - self._mastery_at) < 600:
                return
        try:
            puuid = self.lcu.summoner.get("puuid")
            rows = self.lcu.get_champion_masteries(puuid, limit=80) or []
            mastery = {}
            for r in rows:
                cid = r.get("championId")
                name = self.dragon.champion_name(cid) if cid else None
                if name and not str(name).startswith("Champion "):
                    mastery[name] = {
                        "level": r.get("championLevel"),
                        "points": r.get("championPoints"),
                    }
            with self._lock:
                if mastery:
                    self._mastery = mastery
                    self._mastery_at = now
        except Exception:
            pass

    def draft_analysis(self, role="", allies=None, enemies=None):
        if not self.draft:
            return {}
        return self.draft.team_comp_warnings(allies=allies, enemies=enemies)

    def ban_suggestions(self, role, allies=None, enemies=None):
        if not self.draft:
            return []
        with self._lock:
            owned = set(self._owned_names)
        pool = []
        try:
            pool = self.db.list_pool() if self.db else []
        except Exception:
            pass
        return self.draft.ban_suggestions(role, owned=owned, pool=pool, enemies=enemies)

    def what_should_i_play(self, role, allies=None, enemies=None):
        if not self.draft:
            return self.recommend(role, allies or [], enemies or [])[:5]
        with self._lock:
            owned = set(self._owned_names)
            mastery = dict(self._mastery)
        personal = {}
        try:
            personal = self.db.champion_personal_stats() if self.db else {}
        except Exception:
            pass
        return self.draft.what_should_i_play(role, allies=allies, enemies=enemies, owned=owned, personal=personal, mastery=mastery, recommender=self.recommender)

    def run_draft_ai(self, kind, payload):
        from src.engine.ai_provider import get_provider, AIProviderError
        def work():
            try:
                provider = get_provider()
                if not provider.is_configured():
                    self._set(_draft_ai={"status": "error", "text": "AI not configured. Set AI_PROVIDER/AI_API_KEY in .env."})
                    return
                role = payload.get("role") or ""
                allies = payload.get("allies") or []
                enemies = payload.get("enemies") or []
                analysis = self.draft_analysis(role, allies, enemies) if self.draft else {}
                if kind == "build_explain":
                    champ = payload.get("champion") or "your champion"
                    build = payload.get("build") or {}
                    prompt = f"""Explain this League build briefly (<140 words) for {champ} ({role}).
ENEMY TEAM: {', '.join(enemies) or 'unknown'}
BUILD: keystone {(build.get('runes') or ['?'])[0]}, core {build.get('core')}, boots {build.get('boots')}, situational {build.get('situational')}, spells {build.get('spells')}, skills {build.get('skills')}.
TEAM COMP NOTES: {analysis.get('vs')}
Give: 1) why this setup works, 2) one item/rune to swap vs this enemy comp, 3) one key gameplay tip. Be specific."""
                else:
                    picks = self.what_should_i_play(role, allies, enemies)
                    bans = self.ban_suggestions(role, allies, enemies)
                    prompt = f"""You are a concise League draft coach.
ROLE: {role}. ALLIES LOCKED: {', '.join(allies) or 'none'}. ENEMIES LOCKED: {', '.join(enemies) or 'none'}.
TEAM COMP WARNINGS (approx): {analysis}
TOP PICKS FOR ME (owned/preferred): {[{"champion":p.get("champion"),"reasons":p.get("reasons",[])[:3]} for p in picks[:5]]}
BAN IDEAS: {[b.get("champion") for b in bans[:5]]}
Give (<180 words): 1) best pick from my list and why vs enemies, 2) main win condition/threat, 3) one ban priority if relevant, 4) one drafting caution."""
                text = ""
                def on_chunk(t, meta): self._set(_draft_ai={"status": "analyzing", "text": t, "model": meta.get("model")})
                res = provider.generate(prompt, max_tokens=360, temperature=0.4, stream=True, on_chunk=on_chunk)
                self._set(_draft_ai={"status": "done", "text": (res.get("text") or text).strip(), "model": res.get("model")})
            except Exception as e:
                self._set(_draft_ai={"status": "error", "text": str(e)})
        self._set(_draft_ai={"status": "analyzing", "text": ""})
        threading.Thread(target=work, daemon=True).start()
        return {"status": "analyzing"}

    def all_champions(self):
        out = []
        for name, data in self.store.champions.items():
            out.append({"name": name, "roles": data.get("roles", []), "tier": data.get("tier", {}), "classes": data.get("classes", [])})
        return sorted(out, key=lambda c: c["name"])

    def import_runes(self, champion, role, confirm=False, build=None, option_name=None):
        if not self.lcu.connected:
            return {"success": False, "error": "League client not connected"}
        if not build or not isinstance(build, dict):
            build = self.store.get_build(champion, role)
        if not build:
            return {"success": False, "error": f"No build data for {champion} {role}"}
        resolved = self.dragon.resolve_rune_page(build)
        if not resolved or not resolved.get("ok"):
            msg = (resolved or {}).get("message") or "Could not resolve rune IDs"
            return {"success": False, "error": msg, "missing": (resolved or {}).get("missing", [])}
        suffix = f" {option_name}" if option_name and option_name != "Highest WR" else ""
        page_name = f"LA: {champion} {role.upper()}"[:31]  # LCU name length safety
        preview = self.lcu.rune_import_preview(page_name, safe=SAFE_RUNE_IMPORT, prefix=RUNE_PAGE_PREFIX)
        if SAFE_RUNE_IMPORT and not confirm:
            return {"success": False, "needs_confirmation": True, "preview": preview, "resolved": {"selected_perks": len(resolved.get("selected_perks", []))}}
        result = self.lcu.import_rune_page(
            page_name,
            resolved["primary_style"],
            resolved["sub_style"],
            resolved["selected_perks"],
            safe=SAFE_RUNE_IMPORT,
            prefix=RUNE_PAGE_PREFIX,
        )
        if isinstance(result, dict):
            ok = bool(result.get("ok"))
            lcu_error = result.get("error")
            lcu_status = result.get("status_code")
        else:
            ok = bool(result)
            lcu_error = None
            lcu_status = None
        if ok:
            return {"success": True, "message": f"Imported runes for {champion}{suffix}", "preview": preview}
        detail = f" (HTTP {lcu_status})" if lcu_status else ""
        msg = f"Failed to create rune page{detail}"
        if lcu_error:
            msg += f": {lcu_error}"
        return {"success": False, "error": msg, "preview": preview}


def monitor_loop(app_state):
    print("[Monitor] Watching for League client...")
    was_connected = False
    prev_phase = "None"
    while True:
        try:
            if not app_state.lcu.connected:
                if app_state.lcu.try_connect():
                    name = "?"
                    if app_state.lcu.summoner:
                        name = app_state.lcu.summoner.get("gameName", "Summoner")
                    print(f"[Monitor] Connected — {name}")
                    was_connected = True
                    threading.Thread(target=app_state.refresh_ownership, kwargs={"force": True}, daemon=True).start()
                    threading.Thread(target=app_state.refresh_mastery, kwargs={"force": True}, daemon=True).start()
                else:
                    if was_connected:
                        print("[Monitor] Client disconnected")
                        was_connected = False
                app_state._set(_phase="None", _champ_select=None)
            else:
                phase = app_state.lcu.get_gameflow_phase()
                phase = phase if isinstance(phase, str) else "None"
                champ_select = app_state.lcu.get_champ_select() if phase == "ChampSelect" else None
                my_role = ""
                participants = []
                if champ_select:
                    cs = app_state._parse_champ_select(champ_select)
                    my_role = cs.get("my_position") or ""
                    participants = app_state._participants_from_champ_select(champ_select)
                # "Loading into game": GameStart/InProgress often expose richer participant IDs in gameflow session.
                if phase in ("GameStart", "InProgress") or (phase == "ChampSelect" and not participants):
                    gf = app_state.lcu.get_gameflow_session()
                    gf_participants = app_state._participants_from_gameflow(gf)
                    if gf_participants:
                        merged = {}
                        for p in participants + gf_participants:
                            k = p.get("puuid") or (f"sid:{p.get('summoner_id')}" if p.get("summoner_id") else None) or p.get("name") or f"cid:{p.get('champion_id')}:{p.get('team')}"
                            cur = merged.get(k, {})
                            cur.update({kk: vv for kk, vv in p.items() if vv not in (None, "", 0) or kk in ("is_me", "team", "party_id", "partyId")})
                            merged[k] = cur
                        participants = list(merged.values())
                if phase in ("Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "GameStart", "InProgress"):
                    lobby = app_state.lcu.get_lobby()
                    participants = app_state._annotate_parties(participants, lobby=lobby)
                if app_state.intel and phase in ("ChampSelect", "GameStart", "InProgress"):
                    app_state.intel.set_participants(participants)
                elif app_state.intel and phase in ("None", "Lobby", "Matchmaking", "ReadyCheck", "EndOfGame"):
                    app_state.intel.set_participants([])
                app_state._set(_phase=phase, _champ_select=champ_select, _my_role=my_role or app_state._my_role)

                if phase == "EndOfGame" and prev_phase != "EndOfGame":
                    print("[Monitor] Game ended — collecting stats...")
                    stats = app_state.postgame.collect_stats(app_state.lcu)
                    if stats:
                        me = stats["me"]
                        print(f"[Monitor] {stats['result']} as {me['champion']} ({me['kills']}/{me['deaths']}/{me['assists']})")
                        app_state.postgame.analyze(stats, role=me.get("position") or app_state._my_role)
                        print("[Monitor] Post-game processing started...")
            prev_phase = app_state._phase
        except Exception as e:
            print(f"[Monitor] Error: {e}")
        time.sleep(LCU_POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="Personal League companion app")
    parser.add_argument("--host", default=WEB_HOST)
    parser.add_argument("--port", type=int, default=WEB_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-lcu", action="store_true", help="Disable LCU polling (useful for UI/data development)")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  LEAGUE ADVISOR — PERSONAL COMPANION")
    print("=" * 50)
    print()

    db = CompanionDB()
    dragon = DataDragon().initialize()
    store = ChampionStore().load()
    lcu = LCUConnector()
    recommender = Recommender(store)
    postgame = PostGameAnalyzer(db=db)
    intel = PlayerIntelService(lcu)
    draft = DraftAdvisor(store)
    app_state = AppState(dragon, store, lcu, recommender, postgame, db, intel=intel, draft=draft)

    if postgame.has_key:
        print("  AI Recap: enabled")
    else:
        print("  AI Recap: set GEMINI_API_KEY to enable (stats still saved)")
    print(f"  Safe rune import: {'on' if SAFE_RUNE_IMPORT else 'off'} ({RUNE_PAGE_PREFIX}*)")
    print(f"  Local DB: {db.path}")

    if not args.no_lcu:
        threading.Thread(target=monitor_loop, args=(app_state,), daemon=True).start()
    else:
        print("  LCU polling: disabled")

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Dashboard → {url}")
    print("  Ctrl+C to stop\n")
    if OPEN_BROWSER and not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    server = WebServer(app_state)
    server.run(args.host, args.port)


if __name__ == "__main__":
    main()
