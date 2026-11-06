import json
import os
import requests
from config import CACHE_DIR, RIOT_DDRAGON


class DataDragon:
    """Fetches and caches champion, item, and rune data from Riot's Data Dragon CDN."""

    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.version = None
        self.champions = {}
        self.champion_by_key = {}
        self.items = {}
        self.runes = {}
        self.rune_lookup = {}

    def initialize(self):
        print("[DataDragon] Fetching latest game data...")
        self.version = self._fetch_version()
        print(f"[DataDragon] Patch {self.version}")
        self.champions = self._fetch("champion.json", "champions.json")
        self._build_champion_index()
        self.items = self._fetch("item.json", "items.json")
        self.runes = self._fetch_runes()
        self._build_rune_lookup()
        print(f"[DataDragon] Loaded {len(self.champions)} champions, {len(self.items)} items")
        return self

    def _fetch_version(self):
        cache = os.path.join(CACHE_DIR, "version.txt")
        try:
            resp = requests.get(f"{RIOT_DDRAGON}/api/versions.json", timeout=10)
            resp.raise_for_status()
            v = resp.json()[0]
            with open(cache, "w") as f:
                f.write(v)
            return v
        except Exception:
            if os.path.exists(cache):
                return open(cache).read().strip()
            return "15.8.1"

    def _fetch(self, endpoint, cache_name):
        cache = os.path.join(CACHE_DIR, cache_name)
        try:
            url = f"{RIOT_DDRAGON}/cdn/{self.version}/data/en_US/{endpoint}"
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()["data"]
            with open(cache, "w") as f:
                json.dump(data, f)
            return data
        except Exception:
            if os.path.exists(cache):
                with open(cache) as f:
                    return json.load(f)
            return {}

    def _fetch_runes(self):
        cache = os.path.join(CACHE_DIR, "runes.json")
        try:
            url = f"{RIOT_DDRAGON}/cdn/{self.version}/data/en_US/runesReforged.json"
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            with open(cache, "w") as f:
                json.dump(data, f)
            return data
        except Exception:
            if os.path.exists(cache):
                with open(cache) as f:
                    return json.load(f)
            return []

    def _build_champion_index(self):
        self.champion_by_key = {}
        for cid, cdata in self.champions.items():
            self.champion_by_key[int(cdata["key"])] = {"id": cid, **cdata}

    def _build_rune_lookup(self):
        self.rune_lookup = {}
        if isinstance(self.runes, list):
            for tree in self.runes:
                self.rune_lookup[tree["name"]] = tree
                for slot in tree.get("slots", []):
                    for rune in slot.get("runes", []):
                        self.rune_lookup[rune["name"]] = rune

    def champion_name(self, champion_key):
        c = self.champion_by_key.get(int(champion_key))
        return c["name"] if c else f"Champion {champion_key}"

    def champion_id(self, champion_key):
        c = self.champion_by_key.get(int(champion_key))
        return c["id"] if c else None

    def champion_icon(self, champion_key):
        cid = self.champion_id(champion_key)
        if cid:
            return f"{RIOT_DDRAGON}/cdn/{self.version}/img/champion/{cid}.png"
        return ""

    def champion_key_by_name(self, name):
        for key, c in self.champion_by_key.items():
            if c["name"].lower() == name.lower() or c["id"].lower() == name.lower():
                return key
        return None

    def item_icon(self, item_id):
        return f"{RIOT_DDRAGON}/cdn/{self.version}/img/item/{item_id}.png"

    def item_name(self, item_id):
        item = self.items.get(str(item_id))
        return item["name"] if item else f"Item {item_id}"

    def find_item_id(self, name):
        name_lower = name.lower()
        for iid, idata in self.items.items():
            if idata["name"].lower() == name_lower:
                return int(iid)
        return None

    def rune_icon(self, rune_name):
        rune = self.rune_lookup.get(rune_name)
        if rune and "icon" in rune:
            return f"{RIOT_DDRAGON}/cdn/img/{rune['icon']}"
        return ""

    SHARD_IDS = {
        "adaptive": 5008, "adaptive force": 5008,
        "attack speed": 5005,
        "ability haste": 5007,
        "armor": 5002,
        "magic resist": 5003, "mr": 5003,
        "health": 5001, "hp": 5001,
    }

    def rune_id(self, rune_name):
        rune = self.rune_lookup.get(rune_name)
        return rune["id"] if rune and "id" in rune else None

    def rune_tree_id(self, tree_name):
        if isinstance(self.runes, list):
            for tree in self.runes:
                if tree["name"].lower() == tree_name.lower():
                    return tree["id"]
        return None

    def shard_id(self, shard_name):
        return self.SHARD_IDS.get(shard_name.lower())

    def resolve_rune_page(self, build):
        rune_names = build.get("runes", [])
        trees = build.get("rune_trees", [])
        shards = build.get("shards", [])

        primary_style = self.rune_tree_id(trees[0]) if trees else None
        sub_style = self.rune_tree_id(trees[1]) if len(trees) > 1 else None

        perk_ids = []
        for name in rune_names:
            rid = self.rune_id(name)
            if rid:
                perk_ids.append(rid)

        for shard in shards:
            sid = self.shard_id(shard)
            if sid:
                perk_ids.append(sid)

        if not primary_style or not sub_style or len(perk_ids) < 6:
            return None

        return {
            "primary_style": primary_style,
            "sub_style": sub_style,
            "selected_perks": perk_ids,
        }

    def all_champion_names(self):
        return sorted(c["name"] for c in self.champions.values())
