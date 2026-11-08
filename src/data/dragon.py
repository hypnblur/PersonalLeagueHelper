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
        self.summoner_spells = {}
        self.spell_by_key = {}  # numeric key (e.g. "4") -> spell data

    def initialize(self):
        print("[DataDragon] Fetching latest game data...")
        self.version = self._fetch_version()
        print(f"[DataDragon] Patch {self.version}")
        self.champions = self._fetch("champion.json", "champions.json")
        self._build_champion_index()
        self.items = self._fetch("item.json", "items.json")
        self.runes = self._fetch_runes()
        self._build_rune_lookup()
        self.summoner_spells = self._fetch("summoner.json", "summoner_spells.json")
        self._build_summoner_spell_index()
        print(f"[DataDragon] Loaded {len(self.champions)} champions, {len(self.items)} items, {len(self.summoner_spells)} summoner spells")
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
        self.rune_lookup_lower = {}
        self.rune_meta = {}  # rune name lower -> {id, tree, tree_id, slot}
        if isinstance(self.runes, list):
            for tree in self.runes:
                self.rune_lookup[tree["name"]] = tree
                self.rune_lookup_lower[tree["name"].lower()] = tree
                for si, slot in enumerate(tree.get("slots", [])):
                    for rune in slot.get("runes", []):
                        self.rune_lookup[rune["name"]] = rune
                        self.rune_lookup_lower[rune["name"].lower()] = rune
                        meta = {"id": rune.get("id"), "tree": tree.get("name"), "tree_id": tree.get("id"), "slot": si}
                        self.rune_meta[rune["name"].lower()] = meta

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

    def _build_summoner_spell_index(self):
        self.spell_by_key = {}
        for sid, sdata in (self.summoner_spells or {}).items():
            if not isinstance(sdata, dict):
                continue
            key = str(sdata.get("key") or "")
            if key:
                self.spell_by_key[key] = {"id": sid, **sdata}

    def summoner_spell(self, spell_id):
        """Resolve a summoner spell by numeric id/key (e.g. 4, '4') or DDragon id."""
        if spell_id in (None, "", 0, "0"):
            return None
        s = self.spell_by_key.get(str(spell_id))
        if s:
            return s
        if isinstance(self.summoner_spells, dict):
            s = self.summoner_spells.get(str(spell_id))
            if s:
                return {"id": str(spell_id), **s} if isinstance(s, dict) else None
        return None

    def summoner_spell_name(self, spell_id):
        s = self.summoner_spell(spell_id)
        if s:
            return s.get("name") or f"Spell {spell_id}"
        if spell_id in (None, "", 0, "0"):
            return ""
        return f"Spell {spell_id}"

    def summoner_spell_icon(self, spell_id):
        s = self.summoner_spell(spell_id)
        if not s:
            return ""
        img = (s.get("image") or {}).get("full")
        if not img:
            return ""
        return f"{RIOT_DDRAGON}/cdn/{self.version}/img/spell/{img}"

    def resolve_summoner_spells(self, spell1_id, spell2_id):
        """Return compact spell info for two spell IDs (best-effort)."""
        def one(sid):
            s = self.summoner_spell(sid)
            if not s:
                return None
            return {
                "id": int(s.get("key") or sid) if str(s.get("key") or sid).isdigit() else sid,
                "key": s.get("key"),
                "name": s.get("name"),
                "ddragon_id": s.get("id"),
                "icon": self.summoner_spell_icon(sid),
            }
        spells = [x for x in (one(spell1_id), one(spell2_id)) if x and x.get("name")]
        return spells

    def rune_icon(self, rune_name):
        rune = self.rune_lookup.get(rune_name)
        if rune and "icon" in rune:
            return f"{RIOT_DDRAGON}/cdn/img/{rune['icon']}"
        return ""

    SHARD_IDS = {
        "adaptive": 5008, "adaptive force": 5008, "af": 5008,
        "attack speed": 5005, "as": 5005,
        "ability haste": 5007, "haste": 5007, "ah": 5007,
        "armor": 5002,
        "magic resist": 5003, "magic resistance": 5003, "mr": 5003,
        "health": 5001, "health scaling": 5001, "hp": 5001, "scaling health": 5001,
        "tenacity and slow resist": 5013, "tenacity": 5013, "slow resist": 5013,
        "move speed": 5010, "movement speed": 5010, "ms": 5010,
    }

    # Aliases for renamed/removed runes across patches/Data Dragon naming differences.
    RUNE_ALIASES = {
        # Domination slot 2 / vision row changes
        "eyeball collection": "Deep Ward",
        "ghost poro": "Deep Ward",
        "zombie ward": "Deep Ward",
        # Precision legend row changes
        "legend: tenacity": "Legend: Haste",
        "legend tenacity": "Legend: Haste",
        # Sorcery keystone naming seen in some Data Dragon outputs
        "phase rush": "Stormraider's Surge",
        # Inspiration row changes (common older names)
        "magical footwear (removed)": "Magical Footwear",
        "biscuit delivery": "Magical Footwear",
        "time warp tonic": "Magical Footwear",
    }

    TREE_ALIASES = {
        "inspirations": "Inspiration",
    }

    def _canonical_rune_name(self, name):
        if not name:
            return name
        key = str(name).strip()
        low = key.lower()
        if low in self.RUNE_ALIASES:
            return self.RUNE_ALIASES[low]
        return key

    def _canonical_tree_name(self, name):
        if not name:
            return name
        key = str(name).strip()
        return self.TREE_ALIASES.get(key.lower(), key)

    def _lookup_rune(self, name):
        if not name:
            return None
        canon = self._canonical_rune_name(name)
        rune = self.rune_lookup.get(canon)
        if rune:
            return rune
        return getattr(self, "rune_lookup_lower", {}).get(canon.lower())

    def rune_id(self, rune_name):
        rune = self._lookup_rune(rune_name)
        return rune["id"] if rune and "id" in rune else None

    def rune_tree_id(self, tree_name):
        tree_name = self._canonical_tree_name(tree_name)
        if not tree_name:
            return None
        if isinstance(self.runes, list):
            for tree in self.runes:
                if tree["name"].lower() == str(tree_name).lower():
                    return tree["id"]
        return None

    def shard_id(self, shard_name):
        if not shard_name:
            return None
        return self.SHARD_IDS.get(str(shard_name).strip().lower())

    def resolve_rune_page(self, build):
        """Resolve a build's rune names to LCU perk IDs.

        Returns the classic success shape for compatibility:
        {primary_style, sub_style, selected_perks}
        or a failure shape:
        {ok: False, missing: [...], message: ...}
        """
        rune_names = build.get("runes", []) or []
        trees = build.get("rune_trees", []) or []
        shards = build.get("shards", []) or []

        missing = []
        primary_style = self.rune_tree_id(trees[0]) if len(trees) > 0 else None
        sub_style = self.rune_tree_id(trees[1]) if len(trees) > 1 else None
        if trees and not primary_style:
            missing.append(f"tree:{trees[0]}")
        if len(trees) > 1 and not sub_style:
            missing.append(f"tree:{trees[1]}")

        perk_ids = []
        resolved_names = []
        warnings = []
        for i, name in enumerate(rune_names):
            rid = self.rune_id(name)
            if rid:
                perk_ids.append(rid)
                resolved_names.append(name)
                canon = self._canonical_rune_name(name)
                meta = getattr(self, "rune_meta", {}).get(str(canon).lower())
                if meta and primary_style and sub_style:
                    if i <= 3 and meta.get("tree_id") != primary_style:
                        warnings.append(f"{name} is in {meta.get('tree')}, expected primary tree")
                    if i >= 4 and meta.get("tree_id") != sub_style:
                        warnings.append(f"{name} is in {meta.get('tree')}, expected secondary tree")
                    if i <= 3 and meta.get("slot") != i:
                        warnings.append(f"{name} may be in wrong slot for primary path")
            else:
                missing.append(f"rune:{name}")

        if primary_style and sub_style and primary_style == sub_style:
            missing.append("trees:primary and secondary must differ")

        for shard in shards:
            sid = self.shard_id(shard)
            if sid:
                perk_ids.append(sid)
            else:
                missing.append(f"shard:{shard}")

        # LCU rune pages normally require 9 selected perks (4 primary + 2 secondary + 3 shards).
        if not primary_style or not sub_style or len(perk_ids) < 8 or missing:
            return {
                "ok": False,
                "missing": missing,
                "warnings": warnings,
                "message": "Could not resolve rune page" + (f": {', '.join(missing[:8])}" if missing else ""),
                "primary_style": primary_style,
                "sub_style": sub_style,
                "selected_perks": perk_ids,
            }

        return {
            "ok": True,
            "primary_style": primary_style,
            "sub_style": sub_style,
            "selected_perks": perk_ids,
            "resolved_names": resolved_names,
            "warnings": warnings,
            "missing": [],
        }

    def all_champion_names(self):
        return sorted(c["name"] for c in self.champions.values())
