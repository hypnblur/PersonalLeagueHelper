from src.data.store import ChampionStore
from src.engine.recommender import Recommender


def _recommender():
    s = ChampionStore()
    s.champions = {
        "Ahri": {
            "roles": ["middle"], "classes": ["mage"], "tier": {"middle": "A"},
            "builds": {"middle": {"wr": 52.0, "runes": ["Electrocute"], "core": ["Malignance"], "spells": ["Flash", "Ignite"], "skills": "Q>W>E"}},
            "matchups": {"Lux": 2}, "synergies": ["Jarvan IV"],
        },
        "Zed": {
            "roles": ["middle"], "classes": ["assassin"], "tier": {"middle": "S"},
            "builds": {"middle": {"wr": 49.0, "runes": ["Electrocute"], "core": ["Eclipse"], "spells": ["Flash", "Ignite"], "skills": "Q>E>W"}},
            "matchups": {"Lux": -1}, "synergies": [],
        },
        "Lux": {"roles": ["middle"], "classes": ["mage"], "tier": {"middle": "B"}, "builds": {"middle": {"wr": 50.0}}, "matchups": {}, "synergies": []},
    }
    return Recommender(s)


def test_recommend_excludes_taken_and_banned():
    r = _recommender()
    recs = r.recommend("middle", allies=["Jarvan IV"], enemies=["Lux"], banned=["Zed"])
    names = [x["champion"] for x in recs]
    assert "Zed" not in names
    assert "Lux" not in names
    assert "Ahri" in names


def test_recommend_rewards_counter_matchup():
    r = _recommender()
    recs = r.recommend("middle", allies=[], enemies=["Lux"])
    assert recs[0]["champion"] == "Ahri"
    assert recs[0]["score"] > recs[1]["score"]
