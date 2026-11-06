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

    def get_build(self, champion, role):
        champ = self.get(champion)
        if not champ:
            return None
        builds = champ.get("builds", {})
        build = builds.get(role)
        if build:
            return build
        if builds:
            return next(iter(builds.values()))
        return None

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
