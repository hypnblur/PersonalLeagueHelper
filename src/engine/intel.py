import threading
import time


class PlayerIntelService:
    """Best-effort background enrichment of player rank/winrate/mastery via LCU.

    LCU endpoints and payloads are unofficial and may vary by client version/mode.
    All lookups are tolerant of missing data.
    """

    def __init__(self, lcu, ttl=600):
        self.lcu = lcu
        self.ttl = ttl
        self._lock = threading.Lock()
        self._cache = {}  # key -> {at, data}
        self._inflight = set()
        self._participants = []

    def set_participants(self, participants):
        with self._lock:
            self._participants = list(participants or [])
        for p in self._participants:
            self._ensure(p)

    def snapshot(self):
        with self._lock:
            participants = list(self._participants)
            cache = dict(self._cache)
        out = []
        for p in participants:
            key = self._key(p)
            info = cache.get(key, {}).get("data") if key else None
            row = dict(p)
            row["intel"] = info or {"status": "pending" if key else "unavailable"}
            out.append(row)
        return out

    def _key(self, p):
        return p.get("puuid") or (f"sid:{p.get('summoner_id')}" if p.get("summoner_id") else None) or (f"name:{p.get('name')}" if p.get("name") else None)

    def _fresh(self, key):
        item = self._cache.get(key)
        return item and (time.time() - item["at"] < self.ttl)

    def _ensure(self, p):
        key = self._key(p)
        if not key:
            return
        with self._lock:
            if self._fresh(key) or key in self._inflight:
                return
            self._inflight.add(key)
        threading.Thread(target=self._fetch_one, args=(key, dict(p)), daemon=True).start()

    def _fetch_one(self, key, p):
        try:
            if not self.lcu.connected:
                data = {"status": "disconnected"}
            else:
                data = self._fetch_player(p)
        except Exception as e:
            data = {"status": "error", "message": str(e)}
        with self._lock:
            self._cache[key] = {"at": time.time(), "data": data}
            self._inflight.discard(key)

    def _fetch_player(self, p):
        puuid = p.get("puuid")
        summoner_id = p.get("summoner_id")
        if not puuid and summoner_id:
            s = self.lcu.get_summoner_by_id(summoner_id)
            if isinstance(s, dict):
                puuid = s.get("puuid") or puuid
                p["name"] = p.get("name") or s.get("gameName") or s.get("displayName")
        if not puuid:
            return {"status": "unavailable", "reason": "no identifier exposed by client/mode"}

        ranked = self.lcu.get_ranked_stats(puuid)
        mastery = None
        if p.get("champion_id"):
            mastery = self.lcu.get_champion_mastery(puuid, p.get("champion_id"))

        return {
            "status": "ok",
            "name": p.get("name"),
            "rank": self._parse_rank(ranked),
            "mastery": self._parse_mastery(mastery),
        }

    def _parse_rank(self, ranked):
        if not isinstance(ranked, dict):
            return None
        queues = ranked.get("queues") or ranked.get("queueMap") or {}
        # queues may be a list or dict depending on client shape
        if isinstance(queues, list):
            qmap = {}
            for q in queues:
                if isinstance(q, dict):
                    qmap[q.get("queueType") or q.get("queue")] = q
            queues = qmap
        for qtype in ("RANKED_SOLO_5x5", "RANKED_FLEX_SR"):
            q = queues.get(qtype)
            if not isinstance(q, dict):
                continue
            tier = q.get("tier")
            if not tier or tier in ("NONE", "", None):
                continue
            div = q.get("division") or q.get("rank") or ""
            lp = q.get("leaguePoints")
            wins = q.get("wins") or 0
            losses = q.get("losses") or 0
            games = wins + losses
            wr = round((wins / games) * 100, 1) if games else None
            return {
                "queue": qtype,
                "tier": tier,
                "division": div,
                "lp": lp,
                "wins": wins,
                "losses": losses,
                "games": games,
                "winrate": wr,
                "text": f"{tier} {div} {lp} LP".strip(),
            }
        return {"queue": None, "tier": "UNRANKED", "division": "", "lp": 0, "wins": 0, "losses": 0, "games": 0, "winrate": None, "text": "Unranked"}

    def _parse_mastery(self, mastery):
        if not isinstance(mastery, dict):
            return None
        # tolerate different key casings/shapes
        level = mastery.get("championLevel") or mastery.get("champion_level") or mastery.get("level")
        points = mastery.get("championPoints") or mastery.get("champion_points") or mastery.get("points")
        if level is None and points is None:
            return None
        return {"level": level, "points": points}
