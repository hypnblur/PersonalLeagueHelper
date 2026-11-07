import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

try:
    from google import genai
except Exception:  # optional dependency / runtime environment
    genai = None

try:
    from google.genai import types as genai_types
except Exception:
    genai_types = None

from config import GEMINI_API_KEY, RECAP_MODEL


class PostGameAnalyzer:
    def __init__(self, db=None):
        self._client = None
        self._latest_recap = None
        self._latest_stats = None
        self._analyzing = False
        self._lock = threading.Lock()
        self.db = db

    def _get_client(self):
        if not GEMINI_API_KEY or genai is None:
            return None
        if not self._client:
            self._client = genai.Client(api_key=GEMINI_API_KEY)
        return self._client

    @property
    def has_key(self):
        return bool(GEMINI_API_KEY) and genai is not None

    @property
    def latest_recap(self):
        with self._lock:
            return self._latest_recap

    @property
    def latest_stats(self):
        with self._lock:
            return self._latest_stats

    @property
    def analyzing(self):
        with self._lock:
            return self._analyzing

    def _set(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, f"_{k}", v)

    def collect_stats(self, lcu):
        raw = lcu.get("/lol-end-of-game/v1/eog-stats-block")
        if not raw:
            return None

        local_puuid = None
        if lcu.summoner:
            local_puuid = lcu.summoner.get("puuid")

        my_stats = None
        my_team = []
        enemy_team = []
        game_length = raw.get("gameLength", 0) or 0

        for team in raw.get("teams", []):
            is_my_team = False
            players = []

            for p in team.get("players", []):
                stats = {
                    "summoner": p.get("summonerName", "Unknown"),
                    "champion": p.get("championName", "Unknown"),
                    "kills": p.get("kills", 0),
                    "deaths": p.get("deaths", 0),
                    "assists": p.get("assists", 0),
                    "cs": p.get("minionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                    "gold": p.get("goldEarned", 0),
                    "damage_dealt": p.get("totalDamageDealtToChampions", 0),
                    "damage_taken": p.get("totalDamageTaken", 0),
                    "vision_score": p.get("visionScore", 0),
                    "wards_placed": p.get("wardPlaced", 0),
                    "level": p.get("level", 1),
                    "spell1": p.get("spell1Id", 0),
                    "spell2": p.get("spell2Id", 0),
                    "items": p.get("items", []),
                    "position": p.get("selectedPosition", ""),
                }

                is_me = False
                if local_puuid and p.get("puuid") == local_puuid:
                    is_me = True
                elif lcu.summoner:
                    my_name = lcu.summoner.get("gameName", "") or lcu.summoner.get("displayName", "")
                    if my_name and p.get("summonerName", "").lower() == my_name.lower():
                        is_me = True

                if is_me:
                    my_stats = stats
                    is_my_team = True

                players.append(stats)

            if is_my_team:
                my_team = players
            else:
                enemy_team = players

        if not my_stats:
            return None

        game_result = "Unknown"
        if raw.get("gameId"):
            for team in raw.get("teams", []):
                for p in team.get("players", []):
                    pname = p.get("summonerName", "")
                    if my_stats and pname == my_stats["summoner"]:
                        game_result = "Victory" if team.get("isWinningTeam") else "Defeat"

        minutes = int(game_length) // 60
        cs_per_min = round(my_stats["cs"] / max(minutes, 1), 1)

        latest_stats = {
            "result": game_result,
            "game_length": f"{minutes}:{int(game_length) % 60:02d}",
            "me": my_stats,
            "cs_per_min": cs_per_min,
            "my_team": my_team,
            "enemy_team": enemy_team,
            "raw_game_id": raw.get("gameId"),
        }
        self._set(latest_stats=latest_stats)
        return latest_stats

    def _base_recap(self, stats, status, analysis="", message="", model=None):
        me = stats.get("me") or {}
        recap = {
            "status": status,
            "champion": me.get("champion"),
            "result": stats.get("result"),
            "kda": f"{me.get('kills',0)}/{me.get('deaths',0)}/{me.get('assists',0)}",
            "cs": me.get("cs"),
            "cs_per_min": stats.get("cs_per_min"),
            "damage": me.get("damage_dealt"),
            "vision": me.get("vision_score"),
            "gold": me.get("gold"),
            "analysis": analysis,
        }
        if message:
            recap["message"] = message
        if model:
            recap["model"] = model
        return recap

    def analyze(self, stats, role=""):
        if not stats:
            return {"status": "error", "message": "No game data"}
        # Instant UX: save raw stats and show them before AI responds.
        pending = self._base_recap(stats, "analyzing", analysis="Saving stats and generating AI recap...")
        self._set(latest_stats=stats, latest_recap=pending, analyzing=True)
        self._persist(stats, {"status": "stats_saved", **{k: v for k, v in pending.items() if k != "status"}}, role)

        client = self._get_client()
        if not client:
            recap = self._base_recap(stats, "no_ai", message="Set GEMINI_API_KEY to enable AI analysis. Stats were saved.")
            self._set(latest_recap=recap, analyzing=False)
            self._persist(stats, recap, role)
            return recap

        threading.Thread(target=self._run_analysis, args=(client, stats, role), daemon=True).start()
        return self.latest_recap

    def _persist(self, stats, recap, role):
        if not self.db:
            return
        try:
            self.db.save_match(stats, recap, role=role)
        except Exception as e:
            print(f"[PostGame] Failed to save match: {e}")

    def _run_analysis(self, client, stats, role):
        try:
            me = stats["me"]
            kda = f"{me['kills']}/{me['deaths']}/{me['assists']}"

            teammates = "\n".join(
                f"  - {p['champion']}: {p['kills']}/{p['deaths']}/{p['assists']}, {p['damage_dealt']} dmg, {p['cs']} CS"
                for p in stats["my_team"] if p["summoner"] != me["summoner"]
            )
            enemies = "\n".join(
                f"  - {p['champion']}: {p['kills']}/{p['deaths']}/{p['assists']}, {p['damage_dealt']} dmg"
                for p in stats["enemy_team"]
            )

            prompt = f"""Analyze this League of Legends match. Be direct and specific (<180 words). No fluff.

RESULT: {stats['result']} in {stats['game_length']}
ME ({me['champion']}): KDA {kda}, CS {me['cs']} ({stats['cs_per_min']}/min), champ dmg {me['damage_dealt']:,}, taken {me['damage_taken']:,}, gold {me['gold']:,}, vision {me['vision_score']} ({me['wards_placed']} wards), lvl {me['level']}
MY TEAM:
{teammates}
ENEMY TEAM:
{enemies}

Return:
1) One-line verdict
2) 2 things done well (numbers)
3) 2 improvements (actionable)
4) One {me['champion']}-specific tip"""

            config = None
            if genai_types is not None:
                try:
                    config = genai_types.GenerateContentConfig(
                        max_output_tokens=320,
                        temperature=0.4,
                    )
                except Exception:
                    config = None

            def is_model_error(err):
                s = str(err).lower()
                return any(x in s for x in ["model", "not found", "404", "unsupported", "does not exist", "invalid argument"]) and "api key" not in s and "quota" not in s and "rate" not in s

            models = []
            for m in [RECAP_MODEL, "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]:
                if m and m not in models:
                    models.append(m)

            text = ""
            used_model = None
            last_err = None
            start = time.time()
            for model in models:
                try:
                    self._set(latest_recap=self._base_recap(stats, "analyzing", analysis=f"Generating AI recap ({model})...", model=model))
                    # Streaming first (best perceived speed)
                    used_stream = False
                    try:
                        stream = client.models.generate_content_stream(model=model, contents=prompt, config=config)
                        used_stream = True
                        text = ""
                        last_chunk_at = time.time()
                        for chunk in stream:
                            part = getattr(chunk, "text", None)
                            if part:
                                text += part
                                last_chunk_at = time.time()
                            if time.time() - start > 60:
                                raise TimeoutError("AI recap timed out (60s). Stats are saved; try Re-analyze.")
                            self._set(latest_recap=self._base_recap(stats, "analyzing", analysis=text, model=model))
                        if text.strip():
                            used_model = model
                            break
                    except Exception as se:
                        if used_stream and text.strip() and not is_model_error(se):
                            used_model = model
                            break
                        if is_model_error(se):
                            last_err = se
                            continue
                        # Non-streaming fallback with timeout
                        def _call():
                            return client.models.generate_content(model=model, contents=prompt, config=config)
                        with ThreadPoolExecutor(max_workers=1) as ex:
                            fut = ex.submit(_call)
                            try:
                                response = fut.result(timeout=max(10, 45 - int(time.time() - start)))
                            except FuturesTimeout:
                                raise TimeoutError("AI recap timed out. Stats are saved; try Re-analyze.")
                        text = response.text if getattr(response, "text", None) else ""
                        if text.strip():
                            used_model = model
                            break
                        last_err = se
                except Exception as e:
                    last_err = e
                    if is_model_error(e):
                        continue
                    # non-model error: report (stats already saved)
                    raise

            if not text.strip():
                if last_err:
                    raise last_err
                raise RuntimeError("No analysis generated.")

            recap = self._base_recap(stats, "done", analysis=text.strip(), model=used_model)
            self._set(latest_recap=recap, analyzing=False)
            self._persist(stats, recap, role)
            return
        except (TimeoutError, FuturesTimeout) as e:
            msg = str(e) or "AI recap timed out. Stats are saved; try Re-analyze."
            recap = self._base_recap(stats, "error", message=msg)
            self._set(latest_recap=recap)
            self._persist(stats, recap, role)
        except Exception as e:
            recap = self._base_recap(stats, "error", message=str(e))
            self._set(latest_recap=recap)
            self._persist(stats, recap, role)
        finally:
            self._set(analyzing=False)
