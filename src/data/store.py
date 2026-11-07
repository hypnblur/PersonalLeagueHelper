import json
import os
from config import DATA_DIR


class ChampionStore:
    """Loads and queries champion builds, counters, and synergies from the seed data file."""

    CLASS_COUNTERS_DEFAULT = {
        "assassin":   {"strong_vs": ["mage", "marksman", "enchanter"],         "weak_vs": ["bruiser", "vanguard", "tank"]},
        "bruiser":    {"strong_vs": ["assassin", "tank"],                      "weak_vs": ["marksman", "skirmisher"]},
        "tank":       {"strong_vs": ["assassin"],                              "weak_vs": ["marksman", "bruiser", "skirmisher"]},
        "mage":       {"strong_vs": ["tank", "bruiser"],                       "weak_vs": ["assassin"]},
        "marksman":   {"strong_vs": ["tank", "bruiser"],                       "weak_vs": ["assassin", "vanguard"]},
        "enchanter":  {"strong_vs": ["bruiser"],                               "weak_vs": ["assassin", "vanguard"]},
        "vanguard":   {"strong_vs": ["marksman", "mage", "enchanter"],         "weak_vs": ["bruiser", "skirmisher"]},
        "skirmisher": {"strong_vs": ["bruiser", "tank", "vanguard"],           "weak_vs": ["marksman"]},
        "specialist": {"strong_vs": [],                                        "weak_vs": []},
        "catcher":    {"strong_vs": ["marksman", "mage"],                      "weak_vs": ["vanguard", "bruiser"]},
    }

    def __init__(self):
        self.champions = {}
        self.class_counters = self.CLASS_COUNTERS_DEFAULT.copy()

    def load(self):
        path = os.path.join(DATA_DIR, "champions.json")
        if not os.path.exists(path):
            print(f"[Store] WARNING: {path} not found — recommendations will be limited")
            return self

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.class_counters = data.get("class_counters", self.class_counters)
        self.champions = data.get("champions", {})
        print(f"[Store] Loaded {len(self.champions)} champions")
        return self

    def get(self, name):
        return self.champions.get(name)

    def _normalize_build_entry(self, entry):
        # Support future format: builds[role] = [build, build2, ...]
        if isinstance(entry, list):
            return [b for b in entry if isinstance(b, dict)]
        if isinstance(entry, dict):
            return [entry]
        return []

    def get_build_options(self, champion, role, limit=3):
        """Return up to `limit` build options sorted by WR desc when available.

        Backward compatible with single-build seed data. Adds transparent
        situational variants when only one known build exists.
        """
        champ = self.get(champion)
        if not champ:
            return []
        builds = champ.get("builds", {})
        options = self._normalize_build_entry(builds.get(role))
        if not options and builds:
            # fallback to any role
            options = self._normalize_build_entry(next(iter(builds.values())))
        if not options:
            return []

        # Normalize/sort known options
        normalized = []
        for i, b in enumerate(options):
            nb = dict(b)
            nb.setdefault("name", "Highest WR" if i == 0 else f"Option {i+1}")
            nb.setdefault("source", "seed")
            normalized.append(nb)
        normalized.sort(key=lambda b: (b.get("wr") is not None, b.get("wr", -1)), reverse=True)

        # If seed only has one build, generate honest situational variants (no fabricated WR)
        if len(normalized) == 1:
            base = normalized[0]
            variants = [base]
            situ = base.get("situational") or []
            if situ:
                for idx, item in enumerate(situ[:2], start=2):
                    v = dict(base)
                    core = list(base.get("core") or [])
                    if core:
                        core = core[:-1] + [item]
                    v["core"] = core
                    v["wr"] = None
                    v["pr"] = None
                    v["name"] = f"Situational: {item}"
                    v["note"] = "Variant from seed situational items (WR not rated in seed data)."
                    v["source"] = "derived"
                    variants.append(v)
            # If still short, add boots/rune-agnostic variant marker
            while len(variants) < limit and len(variants) < 3:
                v = dict(base)
                v["wr"] = None
                v["pr"] = None
                v["name"] = ["Highest WR", "Situational: core flex", "Situational: team/adapt"][len(variants)]
                v["note"] = "Adapt core/situational items to enemy damage types and win condition."
                v["source"] = "derived"
                variants.append(v)
            return variants[:limit]

        return normalized[:limit]

    def get_build(self, champion, role):
        options = self.get_build_options(champion, role, limit=1)
        return options[0] if options else None

    def get_tier(self, champion, role):
        champ = self.get(champion)
        if champ:
            return champ.get("tier", {}).get(role, "B")
        return "C"

    def get_synergies(self, champion):
        champ = self.get(champion)
        return champ.get("synergies", []) if champ else []

    def get_matchup_score(self, champion, opponent):
        champ = self.get(champion)
        if champ:
            score = champ.get("matchups", {}).get(opponent)
            if score is not None:
                return score

        opp = self.get(opponent)
        if opp:
            score = opp.get("matchups", {}).get(champion)
            if score is not None:
                return -score

        return self._class_matchup(champion, opponent)

    def _class_matchup(self, champ_name, opp_name):
        champ = self.get(champ_name)
        opp = self.get(opp_name)
        if not champ or not opp:
            return 0

        champ_classes = set(champ.get("classes", []))
        opp_classes = set(opp.get("classes", []))

        score = 0
        for cls in champ_classes:
            info = self.class_counters.get(cls, {})
            if opp_classes & set(info.get("strong_vs", [])):
                score += 1
            if opp_classes & set(info.get("weak_vs", [])):
                score -= 1
        return max(-2, min(2, score))

    def champions_for_role(self, role):
        return [
            (name, data)
            for name, data in self.champions.items()
            if role in data.get("roles", [])
        ]

    def all_names(self):
        return sorted(self.champions.keys())
