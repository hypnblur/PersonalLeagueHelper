import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LCU_POLL_INTERVAL, WEB_HOST, WEB_PORT
from src.data.dragon import DataDragon
from src.data.store import ChampionStore
from src.lcu.connector import LCUConnector
from src.engine.recommender import Recommender
from src.engine.postgame import PostGameAnalyzer
from src.web.server import WebServer


class AppState:
    def __init__(self, dragon, store, lcu, recommender, postgame):
        self.dragon = dragon
        self.store = store
        self.lcu = lcu
        self.recommender = recommender
        self.postgame = postgame
        self._champ_select = None
        self._phase = "None"

    def snapshot(self):
        state = {
            "lcu_connected": self.lcu.connected,
            "phase": self._phase,
            "summoner": None,
            "patch": self.dragon.version,
            "champ_select": None,
            "recommendations": [],
            "recap_available": self.postgame.latest_recap is not None,
            "recap_analyzing": self.postgame.analyzing,
            "recap_has_key": self.postgame.has_key,
        }

        if self.lcu.connected and self.lcu.summoner:
            s = self.lcu.summoner
            state["summoner"] = {
                "name": s.get("gameName", s.get("displayName", "Summoner")),
                "tag": s.get("tagLine", ""),
                "level": s.get("summonerLevel", 0),
            }

        if self._champ_select:
            cs = self._parse_champ_select(self._champ_select)
            state["champ_select"] = cs
            allies = [p["champion"] for p in cs["my_team"] if p["champion"] and not p["is_me"]]
            enemies = [p["champion"] for p in cs["enemy_team"] if p["champion"]]
            role = cs.get("my_position", "")
            if role:
                state["recommendations"] = self.recommender.recommend(role, allies, enemies)

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
            my_team.append({
                "champion": self.dragon.champion_name(cid) if cid else "",
                "champion_id": cid,
                "position": pos,
                "is_me": is_me,
                "icon": self.dragon.champion_icon(cid) if cid else "",
            })

        for m in session.get("theirTeam", []):
            cid = m.get("championId", 0) or m.get("championPickIntent", 0)
            enemy_team.append({
                "champion": self.dragon.champion_name(cid) if cid else "",
                "champion_id": cid,
                "position": m.get("assignedPosition", ""),
                "icon": self.dragon.champion_icon(cid) if cid else "",
            })

        return {"my_team": my_team, "enemy_team": enemy_team, "my_position": my_pos}

    def build_info(self, champion, role=None):
        champ = self.store.get(champion)
        if not champ:
            return {"error": f"No data for '{champion}'"}
        if not role:
            role = champ.get("roles", ["mid"])[0]
        build = self.store.get_build(champion, role)
        if not build:
            return {"error": f"No build for {champion} {role}"}
        return {
            "champion": champion,
            "role": role,
            "tier": champ.get("tier", {}).get(role, "?"),
            "build": build,
        }

    def all_champions(self):
        out = []
        for name, data in self.store.champions.items():
            out.append({"name": name, "roles": data.get("roles", []), "tier": data.get("tier", {}), "classes": data.get("classes", [])})
        return sorted(out, key=lambda c: c["name"])

    def import_runes(self, champion, role):
        if not self.lcu.connected:
            return {"success": False, "error": "League client not connected"}
        build = self.store.get_build(champion, role)
        if not build:
            return {"success": False, "error": f"No build data for {champion} {role}"}

        resolved = self.dragon.resolve_rune_page(build)
        if not resolved:
            return {"success": False, "error": "Could not resolve rune IDs"}

        page_name = f"LA: {champion} {role.upper()}"
        ok = self.lcu.import_rune_page(
            page_name,
            resolved["primary_style"],
            resolved["sub_style"],
            resolved["selected_perks"],
        )
        if ok:
            return {"success": True, "message": f"Imported runes for {champion}"}
        return {"success": False, "error": "Failed to create rune page — check client"}


def monitor_loop(app_state):
    print("[Monitor] Watching for League client...")
    was_connected = False
    prev_phase = "None"
    while True:
        if not app_state.lcu.connected:
            if app_state.lcu.try_connect():
                name = "?"
                if app_state.lcu.summoner:
                    name = app_state.lcu.summoner.get("gameName", "Summoner")
                print(f"[Monitor] Connected — {name}")
                was_connected = True
            else:
                if was_connected:
                    print("[Monitor] Client disconnected")
                    was_connected = False
            app_state._phase = "None"
            app_state._champ_select = None
        else:
            phase = app_state.lcu.get_gameflow_phase()
            app_state._phase = phase if isinstance(phase, str) else "None"
            if app_state._phase == "ChampSelect":
                app_state._champ_select = app_state.lcu.get_champ_select()
            else:
                app_state._champ_select = None

            if app_state._phase == "EndOfGame" and prev_phase != "EndOfGame":
                print("[Monitor] Game ended — collecting stats...")
                stats = app_state.postgame.collect_stats(app_state.lcu)
                if stats:
                    print(f"[Monitor] {stats['result']} as {stats['me']['champion']} "
                          f"({stats['me']['kills']}/{stats['me']['deaths']}/{stats['me']['assists']})")
                    app_state.postgame.analyze(stats)
                    print("[Monitor] AI analysis started...")

        prev_phase = app_state._phase
        time.sleep(LCU_POLL_INTERVAL)


def main():
    print()
    print("=" * 50)
    print("  LEAGUE ADVISOR")
    print("=" * 50)
    print()

    dragon = DataDragon().initialize()
    store = ChampionStore().load()
    lcu = LCUConnector()
    recommender = Recommender(store)
    postgame = PostGameAnalyzer()
    app_state = AppState(dragon, store, lcu, recommender, postgame)

    if postgame.has_key:
        print("  AI Recap: enabled")
    else:
        print("  AI Recap: set GEMINI_API_KEY to enable")

    threading.Thread(target=monitor_loop, args=(app_state,), daemon=True).start()

    server = WebServer(app_state)
    print(f"\n  Dashboard → http://{WEB_HOST}:{WEB_PORT}")
    print("  Ctrl+C to stop\n")
    server.run(WEB_HOST, WEB_PORT)


if __name__ == "__main__":
    main()
