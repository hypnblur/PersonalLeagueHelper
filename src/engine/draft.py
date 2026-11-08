"""Draft / pre-game analysis: team comp warnings, ban suggestions, what-to-play."""

from __future__ import annotations


DAMAGE_HINT = {
    "mage": "AP",
    "marksman": "AD",
    "assassin": "Burst",
    "bruiser": "Mixed/AD",
    "tank": "Mixed",
    "vanguard": "Engage/Tank",
    "enchanter": "Utility",
    "catcher": "Pick/Utility",
    "skirmisher": "AD/Duel",
    "specialist": "Mixed",
}
FRONTLINE = {"tank", "vanguard", "bruiser"}
ENGAGE = {"vanguard", "tank", "catcher"}
WAVECLEAR_HINT = {"mage"}  # rough


class DraftAdvisor:
    def __init__(self, store):
        self.store = store

    def team_comp_warnings(self, allies=None, enemies=None):
        allies = [c for c in (allies or []) if c]
        enemies = [c for c in (enemies or []) if c]
        return {
            "ally": self._analyze_comp(allies, "Your team"),
            "enemy": self._analyze_comp(enemies, "Enemy team"),
            "vs": self._vs_notes(allies, enemies),
        }

    def _classes_for(self, champ_name):
        c = self.store.get(champ_name) or {}
        return list(c.get("classes") or [])

    def _analyze_comp(self, champs, label):
        if not champs:
            return {"label": label, "champs": [], "damage": {}, "warnings": [], "notes": []}
        classes = []
        dmg = {"AD": 0, "AP": 0, "Mixed": 0, "Utility": 0}
        frontline = 0
        engage = 0
        for name in champs:
            cls = self._classes_for(name)
            classes.extend(cls)
            has_dmg = False
            for cl in cls:
                h = DAMAGE_HINT.get(cl, "")
                if "AP" in h:
                    dmg["AP"] += 1; has_dmg = True
                elif "AD" in h or "Burst" in h or "Duel" in h:
                    dmg["AD"] += 1; has_dmg = True
                elif "Mixed" in h or "Engage/Tank" in h:
                    dmg["Mixed"] += 1; has_dmg = True
                elif "Utility" in h or "Pick" in h:
                    dmg["Utility"] += 1
                if cl in FRONTLINE:
                    frontline += 1
                if cl in ENGAGE:
                    engage += 1
            if not has_dmg and cls:
                dmg["Mixed"] += 1
        total = max(len(champs), 1)
        warnings = []
        notes = []
        ad_share = (dmg["AD"] / total)
        ap_share = (dmg["AP"] / total)
        if ad_share >= 0.6:
            warnings.append("Heavy AD damage — enemies can stack armor effectively.")
        if ap_share >= 0.6:
            warnings.append("Heavy AP damage — enemies can stack magic resist effectively.")
        if frontline == 0 and len(champs) >= 3:
            warnings.append("Little/no clear frontline — vulnerable to engage and dive.")
        elif frontline >= 3:
            notes.append("Strong frontline/tank presence.")
        if engage == 0 and len(champs) >= 3:
            warnings.append("Limited hard engage — may struggle to start fights.")
        elif engage >= 2:
            notes.append("Has engage tools.")
        if dmg["Utility"] >= 2:
            notes.append("Good utility/peel potential.")
        return {
            "label": label,
            "champs": champs,
            "damage": dmg,
            "frontline": frontline,
            "engage": engage,
            "warnings": warnings,
            "notes": notes,
            "disclaimer": "Estimated from champion classes (approximate).",
        }

    def _vs_notes(self, allies, enemies):
        if not allies or not enemies:
            return []
        a = self._analyze_comp(allies, "A")
        e = self._analyze_comp(enemies, "E")
        notes = []
        if e["damage"].get("AP", 0) >= 3:
            notes.append("Enemy team is AP-heavy: consider MR/anti-burst options.")
        if e["damage"].get("AD", 0) >= 3:
            notes.append("Enemy team is AD-heavy: consider armor/anti-crit options.")
        if e["engage"] >= 2 and a["frontline"] == 0:
            notes.append("Enemy has engage but you lack frontline — prioritize positioning/disengage.")
        if a["engage"] >= 2 and e["frontline"] == 0:
            notes.append("You have engage into low-frontline enemies — look for picks.")
        return notes

    def ban_suggestions(self, role, owned=None, pool=None, enemies=None, limit=8):
        """Suggest bans: threats for your role/pool, or strong into locked enemies' gaps."""
        owned = set(owned or [])
        pool_names = {p.get("champion") if isinstance(p, dict) else p for p in (pool or [])}
        my_pool = owned | {n for n in pool_names if n}
        candidates = self.store.champions_for_role(role) if role else list(self.store.champions.items())
        scores = []
        for name, data in candidates:
            if not name:
                continue
            threat = 0.0
            reasons = []
            tier = self.store.get_tier(name, role) if role else "B"
            tier_map = {"S": 4, "A": 2.5, "B": 1, "C": 0, "D": -1}
            threat += tier_map.get(tier, 1)
            if tier in ("S", "A"):
                reasons.append(f"{tier}-tier {role or 'pick'}")
            # If this champ counters many of my owned/pool picks, banning it helps me
            pool_counter = 0
            for mine in list(my_pool)[:12]:
                if self.store.get_matchup_score(name, mine) >= 1:
                    pool_counter += 1
            if pool_counter >= 2:
                threat += pool_counter * 1.8
                reasons.append(f"Counters {pool_counter} of your pool picks")
            build = self.store.get_build(name, role) if role else None
            if build and build.get("wr") and build["wr"] >= 51.5:
                threat += (build["wr"] - 50) * 0.6
            if enemies:
                # if enemies haven't locked it, banning champs that synergize with them or counter their obvious needs is situational; keep simple
                pass
            if threat > 1.5:
                scores.append({"champion": name, "score": round(threat, 1), "reasons": reasons or ["Common threat"], "tier": tier})
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:limit]

    def what_should_i_play(self, role, allies=None, enemies=None, owned=None, personal=None, mastery=None, recommender=None, limit=5):
        allies = allies or []
        enemies = enemies or []
        owned = set(owned or [])
        personal = personal or {}
        mastery = mastery or {}  # champ -> {level, points}
        if recommender:
            recs = recommender.recommend(role, allies, enemies, owned=owned or None, personal=personal)
        else:
            recs = []
        # Filter/boost by owned and mastery
        out = []
        for r in recs:
            name = r["champion"]
            if owned and name not in owned:
                continue
            m = mastery.get(name) or {}
            if m.get("level") is not None:
                r = dict(r)
                r.setdefault("reasons", []).append(f"Mastery {m.get('level')}")
            out.append(r)
            if len(out) >= limit:
                break
        # If ownership filter removed everything, fall back to top recs with note
        if not out and recs:
            out = [dict(r, note="Not marked owned; showing best overall into enemy comp") for r in recs[:limit]]
        return out

    def adaptive_build(self, store, champion, role, enemies=None):
        """Suggest an adaptive 4th build option vs enemy team (transparent, derived)."""
        options = store.get_build_options(champion, role, limit=1)
        if not options:
            return None
        base = dict(options[0])
        enemies = [e for e in (enemies or []) if e]
        ap = ad = 0
        for e in enemies:
            for cl in (store.get(e) or {}).get("classes") or []:
                if cl == "mage":
                    ap += 2
                elif cl == "marksman":
                    ad += 2
                elif cl == "assassin":
                    ap += 1; ad += 1
                elif cl in ("bruiser", "skirmisher"):
                    ad += 1
        situ = list(base.get("situational") or [])
        pick = None
        reason = "Balanced into enemy comp"
        if ap > ad + 1:
            pick = next((i for i in situ if any(x in i.lower() for x in ["maw", "banshee", "force of nature", "wit's", "mercur", "kaenic", "spirit visage"])), None)
            reason = "Enemy comp leans AP/burst — prioritize MR/survivability situational."
        elif ad > ap + 1:
            pick = next((i for i in situ if any(x in i.lower() for x in ["guardian angel", "randuin", "frozen heart", "dead man", "thornmail", "plated", "death's dance", "jak'sho"])), None)
            reason = "Enemy comp leans AD — prioritize armor/durability situational."
        if pick:
            core = list(base.get("core") or [])
            if core and pick not in core:
                core = core[:-1] + [pick]
            base["core"] = core
            base["name"] = f"Adaptive: vs enemy comp"
        else:
            base["name"] = "Adaptive: vs enemy comp"
        base["wr"] = None
        base["pr"] = None
        base["source"] = "adaptive"
        base["note"] = reason + " (derived from seed situational items; WR not rated.)"
        return base
