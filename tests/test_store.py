from src.data.store import ChampionStore


def _store():
    s = ChampionStore()
    s.champions = {
        "Ahri": {
            "roles": ["middle"],
            "classes": ["mage"],
            "tier": {"middle": "A"},
            "builds": {"middle": {"runes": ["Electrocute"], "core": ["Luden"], "wr": 51.0}},
            "matchups": {"Zed": -1, "Lux": 2},
            "synergies": ["Jarvan IV"],
        },
        "Zed": {
            "roles": ["middle"],
            "classes": ["assassin"],
            "tier": {"middle": "S"},
            "builds": {"middle": {"wr": 49.5}},
            "matchups": {},
            "synergies": [],
        },
        "Lux": {"roles": ["middle"], "classes": ["mage"], "tier": {"middle": "B"}, "builds": {"middle": {"wr": 50.0}}, "matchups": {}, "synergies": []},
        "Jarvan IV": {"roles": ["jungle"], "classes": ["vanguard"], "tier": {"jungle": "A"}, "builds": {"jungle": {"wr": 50.0}}, "matchups": {}, "synergies": []},
    }
    return s


def test_get_build_fallbacks_to_available_role_build():
    s = _store()
    build = s.get_build("Ahri", "top")
    assert build is not None
    assert build["core"] == ["Luden"]


def test_get_matchup_score_uses_explicit_and_reverse():
    s = _store()
    assert s.get_matchup_score("Ahri", "Lux") == 2
    assert s.get_matchup_score("Lux", "Ahri") == -2
    assert s.get_matchup_score("Ahri", "Zed") == -1


def test_champions_for_role():
    s = _store()
    names = [n for n, _ in s.champions_for_role("middle")]
    assert set(names) == {"Ahri", "Zed", "Lux"}
