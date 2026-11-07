from src.data.dragon import DataDragon


def _dragon():
    d = DataDragon()
    d.version = "15.1.1"
    d.runes = [
        {
            "id": 8100,
            "name": "Domination",
            "icon": "perk-images/Styles/7200_Domination.png",
            "slots": [
                {"runes": [{"id": 8112, "name": "Electrocute", "icon": "perk-images/Styles/Domination/Electrocute/Electrocute.png"}]},
                {"runes": [{"id": 8126, "name": "Cheap Shot", "icon": "x"}]},
                {"runes": [{"id": 8138, "name": "Eyeball Collection", "icon": "x"}]},
                {"runes": [{"id": 8105, "name": "Relentless Hunter", "icon": "x"}]},
            ],
        },
        {
            "id": 8300,
            "name": "Inspiration",
            "slots": [
                {"runes": [{"id": 8304, "name": "Magical Footwear", "icon": "x"}]},
                {"runes": [{"id": 8347, "name": "Cosmic Insight", "icon": "x"}]},
            ],
        },
    ]
    d._build_rune_lookup()
    return d


def test_resolve_rune_page_returns_ids_and_shards():
    d = _dragon()
    build = {
        "runes": ["Electrocute", "Cheap Shot", "Eyeball Collection", "Relentless Hunter", "Magical Footwear", "Cosmic Insight"],
        "rune_trees": ["Domination", "Inspiration"],
        "shards": ["Adaptive", "Health", "Armor"],
    }
    resolved = d.resolve_rune_page(build)
    assert resolved is not None
    assert resolved["primary_style"] == 8100
    assert resolved["sub_style"] == 8300
    assert resolved["selected_perks"][:6] == [8112, 8126, 8138, 8105, 8304, 8347]
    assert resolved["selected_perks"][6:] == [5008, 5001, 5002]


def test_shard_and_rune_resolution():
    d = _dragon()
    assert d.shard_id("mr") == 5003
    assert d.rune_id("Electrocute") == 8112
    assert d.rune_tree_id("domination") == 8100
