import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from config import DB_PATH as DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH


class CompanionDB:
    def __init__(self, path=None):
        self.path = path or DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self):
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    created_at INTEGER NOT NULL,
                    result TEXT,
                    champion TEXT,
                    role TEXT,
                    game_length TEXT,
                    kills INTEGER,
                    deaths INTEGER,
                    assists INTEGER,
                    cs INTEGER,
                    cs_per_min REAL,
                    damage INTEGER,
                    damage_taken INTEGER,
                    gold INTEGER,
                    vision INTEGER,
                    wards_placed INTEGER,
                    damage_share REAL,
                    stats_json TEXT,
                    recap_json TEXT
                );
                CREATE TABLE IF NOT EXISTS champ_pool (
                    champion TEXT PRIMARY KEY,
                    role TEXT,
                    priority INTEGER DEFAULT 0,
                    notes TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    category TEXT DEFAULT 'general',
                    champion TEXT DEFAULT '',
                    content TEXT NOT NULL
                );
                """
            )
            self._migrate_matches(conn)

    def _migrate_matches(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()}
        if "game_id" not in cols:
            try:
                conn.execute("ALTER TABLE matches ADD COLUMN game_id TEXT")
            except Exception:
                pass
        # Backfill game_id from stored stats_json
        try:
            rows = conn.execute("SELECT id, stats_json FROM matches WHERE game_id IS NULL OR game_id = ''").fetchall()
            for r in rows:
                gid = None
                try:
                    s = json.loads(r["stats_json"] or "{}") or {}
                    gid = s.get("raw_game_id") or s.get("gameId") or s.get("game_id")
                except Exception:
                    gid = None
                if gid is not None and str(gid).strip():
                    conn.execute("UPDATE matches SET game_id=? WHERE id=?", (str(gid).strip(), r["id"]))
        except Exception:
            pass
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_game_id ON matches(game_id) WHERE game_id IS NOT NULL AND game_id != ''")
        except Exception:
            pass
        self._dedupe_matches(conn)

    def _dedupe_matches(self, conn):
        # Keep best row per game_id: prefer non-zero core stats, then done recap/analysis, then newest id.
        try:
            dupes = conn.execute(
                "SELECT game_id FROM matches WHERE game_id IS NOT NULL AND game_id != '' GROUP BY game_id HAVING COUNT(*) > 1"
            ).fetchall()
            for d in dupes:
                gid = d["game_id"]
                rows = conn.execute("SELECT * FROM matches WHERE game_id=? ORDER BY id ASC", (gid,)).fetchall()
                def score(r):
                    core = (r["kills"] or 0) + (r["deaths"] or 0) + (r["assists"] or 0) + (r["cs"] or 0) + (r["damage"] or 0)
                    has_analysis = 0
                    try:
                        rec = json.loads(r["recap_json"] or "{}") or {}
                        if rec.get("status") == "done" and (rec.get("analysis") or "").strip():
                            has_analysis = 2
                        elif rec.get("status") in ("error", "no_ai", "stats_saved"):
                            has_analysis = 1
                    except Exception:
                        pass
                    return (1 if core > 0 else 0, has_analysis, r["id"])
                best = max(rows, key=score)
                for r in rows:
                    if r["id"] != best["id"]:
                        conn.execute("DELETE FROM matches WHERE id=?", (r["id"],))
        except Exception:
            pass

    # --- settings ---
    def get_setting(self, key, default=None):
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]

    def set_setting(self, key, value):
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def all_settings(self):
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out

    # --- matches ---
    def _stats_quality(self, kills, deaths, assists, cs, damage):
        return int(kills or 0) + int(deaths or 0) + int(assists or 0) + int(cs or 0) + int(damage or 0)

    def save_match(self, stats, recap=None, role=""):
        if not stats:
            return None
        me = stats.get("me") or {}
        team = stats.get("my_team") or []
        team_damage = sum(p.get("damage_dealt", 0) for p in team) or 0
        my_damage = me.get("damage_dealt", 0) or 0
        damage_share = round((my_damage / team_damage) * 100, 1) if team_damage else None
        game_id = stats.get("raw_game_id") or stats.get("gameId") or stats.get("game_id")
        game_id = str(game_id).strip() if game_id is not None and str(game_id).strip() else None
        vals = {
            "game_id": game_id,
            "created_at": int(time.time()),
            "result": stats.get("result"),
            "champion": me.get("champion"),
            "role": role or me.get("position") or "",
            "game_length": stats.get("game_length"),
            "kills": int(me.get("kills", 0) or 0),
            "deaths": int(me.get("deaths", 0) or 0),
            "assists": int(me.get("assists", 0) or 0),
            "cs": int(me.get("cs", 0) or 0),
            "cs_per_min": stats.get("cs_per_min"),
            "damage": int(my_damage or 0),
            "damage_taken": int(me.get("damage_taken", 0) or 0),
            "gold": int(me.get("gold", 0) or 0),
            "vision": int(me.get("vision_score", 0) or 0),
            "wards_placed": int(me.get("wards_placed", 0) or 0),
            "damage_share": damage_share,
            "stats_json": json.dumps(stats),
            "recap_json": json.dumps(recap) if recap else None,
        }
        with self._lock, self._conn() as conn:
            if game_id:
                existing = conn.execute("SELECT * FROM matches WHERE game_id=?", (game_id,)).fetchone()
                if existing:
                    ex_q = self._stats_quality(existing["kills"], existing["deaths"], existing["assists"], existing["cs"], existing["damage"])
                    new_q = self._stats_quality(vals["kills"], vals["deaths"], vals["assists"], vals["cs"], vals["damage"])
                    # Don't overwrite good stats with an all-zero re-collection.
                    if new_q == 0 and ex_q > 0:
                        for k in ("result","champion","role","game_length","kills","deaths","assists","cs","cs_per_min","damage","damage_taken","gold","vision","wards_placed","damage_share","stats_json"):
                            vals[k] = existing[k]
                    # Keep better recap (prefer done+analysis)
                    if vals["recap_json"] is None and existing["recap_json"]:
                        vals["recap_json"] = existing["recap_json"]
                    vals["created_at"] = existing["created_at"] or vals["created_at"]
                    conn.execute(
                        """UPDATE matches SET game_id=:game_id,created_at=:created_at,result=:result,champion=:champion,role=:role,game_length=:game_length,
                           kills=:kills,deaths=:deaths,assists=:assists,cs=:cs,cs_per_min=:cs_per_min,damage=:damage,damage_taken=:damage_taken,
                           gold=:gold,vision=:vision,wards_placed=:wards_placed,damage_share=:damage_share,stats_json=:stats_json,recap_json=:recap_json
                           WHERE id=:id""",
                        {**vals, "id": existing["id"]},
                    )
                    return existing["id"]
            cur = conn.execute(
                """INSERT INTO matches(game_id,created_at,result,champion,role,game_length,kills,deaths,assists,cs,cs_per_min,damage,damage_taken,gold,vision,wards_placed,damage_share,stats_json,recap_json)
                   VALUES(:game_id,:created_at,:result,:champion,:role,:game_length,:kills,:deaths,:assists,:cs,:cs_per_min,:damage,:damage_taken,:gold,:vision,:wards_placed,:damage_share,:stats_json,:recap_json)""",
                vals,
            )
            return cur.lastrowid

    def recent_matches(self, limit=20):
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM matches ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def champion_personal_stats(self, limit=200):
        matches = self.recent_matches(limit)
        out = {}
        for m in matches:
            c = m.get("champion") or "Unknown"
            s = out.setdefault(c, {"games": 0, "wins": 0})
            s["games"] += 1
            if m.get("result") == "Victory":
                s["wins"] += 1
        for c, s in out.items():
            s["wr"] = round((s["wins"] / s["games"]) * 100, 1) if s["games"] else None
        return out

    def insights(self, limit=30):
        matches = self.recent_matches(limit)
        if not matches:
            return {"count": 0}
        n = len(matches)
        wins = sum(1 for m in matches if m.get("result") == "Victory")

        def avg(key):
            vals = [m[key] for m in matches if m.get(key) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        def kda(m):
            d = m.get("deaths") or 0
            return ((m.get("kills") or 0) + (m.get("assists") or 0)) / max(d, 1)

        by_champ = {}
        for m in matches:
            c = m.get("champion") or "Unknown"
            by_champ.setdefault(c, {"games": 0, "wins": 0})
            by_champ[c]["games"] += 1
            if m.get("result") == "Victory":
                by_champ[c]["wins"] += 1
        champs = []
        for c, v in by_champ.items():
            champs.append({"champion": c, "games": v["games"], "wins": v["wins"], "wr": round(v["wins"] / v["games"] * 100, 1)})
        champs.sort(key=lambda x: (-x["games"], -x["wr"]))

        return {
            "count": n,
            "wins": wins,
            "losses": n - wins,
            "winrate": round(wins / n * 100, 1),
            "avg_kda": round(sum(kda(m) for m in matches) / n, 2),
            "avg_kills": avg("kills"),
            "avg_deaths": avg("deaths"),
            "avg_assists": avg("assists"),
            "avg_cs": avg("cs"),
            "avg_cs_per_min": avg("cs_per_min"),
            "avg_vision": avg("vision"),
            "avg_damage": avg("damage"),
            "avg_damage_share": avg("damage_share"),
            "by_champion": champs[:8],
            "recent": [
                {
                    "id": m["id"],
                    "created_at": m["created_at"],
                    "result": m.get("result"),
                    "champion": m.get("champion"),
                    "kda": f"{m.get('kills',0)}/{m.get('deaths',0)}/{m.get('assists',0)}",
                    "cs_per_min": m.get("cs_per_min"),
                    "vision": m.get("vision"),
                }
                for m in matches[:10]
            ],
        }

    # --- champ pool ---
    def list_pool(self):
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM champ_pool ORDER BY priority DESC, champion").fetchall()
        return [dict(r) for r in rows]

    def upsert_pool(self, champion, role="", priority=0, notes=""):
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO champ_pool(champion,role,priority,notes) VALUES(?,?,?,?) ON CONFLICT(champion) DO UPDATE SET role=excluded.role,priority=excluded.priority,notes=excluded.notes",
                (champion, role, int(priority), notes),
            )

    def remove_pool(self, champion):
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM champ_pool WHERE champion=?", (champion,))

    # --- notes ---
    def add_note(self, content, category="general", champion=""):
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO notes(created_at,category,champion,content) VALUES(?,?,?,?)",
                (int(time.time()), category, champion, content),
            )
            return cur.lastrowid

    def list_notes(self, limit=50):
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, note_id):
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM notes WHERE id=?", (int(note_id),))
