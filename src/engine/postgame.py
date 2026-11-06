import threading
from google import genai
from config import GEMINI_API_KEY, RECAP_MODEL


class PostGameAnalyzer:
    def __init__(self):
        self._client = None
        self._latest_recap = None
        self._latest_stats = None
        self._analyzing = False

    def _get_client(self):
        if not GEMINI_API_KEY:
            return None
        if not self._client:
            self._client = genai.Client(api_key=GEMINI_API_KEY)
        return self._client

    @property
    def has_key(self):
        return bool(GEMINI_API_KEY)

    @property
    def latest_recap(self):
        return self._latest_recap

    @property
    def latest_stats(self):
        return self._latest_stats

    @property
    def analyzing(self):
        return self._analyzing

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
        game_length = raw.get("gameLength", 0)

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
                    my_name = lcu.summoner.get("gameName", "")
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

        minutes = game_length // 60
        cs_per_min = round(my_stats["cs"] / max(minutes, 1), 1)

        self._latest_stats = {
            "result": game_result,
            "game_length": f"{minutes}:{game_length % 60:02d}",
            "me": my_stats,
            "cs_per_min": cs_per_min,
            "my_team": my_team,
            "enemy_team": enemy_team,
        }

        return self._latest_stats

    def analyze(self, stats):
        client = self._get_client()
        if not client or not stats:
            self._latest_recap = {
                "status": "error",
                "message": "No API key set — add GEMINI_API_KEY to your environment",
            }
            return self._latest_recap

        self._analyzing = True
        self._latest_recap = {"status": "analyzing"}
        threading.Thread(target=self._run_analysis, args=(client, stats), daemon=True).start()
        return self._latest_recap

    def _run_analysis(self, client, stats):
        try:
            me = stats["me"]
            kda = f"{me['kills']}/{me['deaths']}/{me['assists']}"

            teammates = "\n".join(
                f"  - {p['champion']}: {p['kills']}/{p['deaths']}/{p['assists']}, "
                f"{p['damage_dealt']} dmg, {p['cs']} CS"
                for p in stats["my_team"] if p["summoner"] != me["summoner"]
            )
            enemies = "\n".join(
                f"  - {p['champion']}: {p['kills']}/{p['deaths']}/{p['assists']}, "
                f"{p['damage_dealt']} dmg"
                for p in stats["enemy_team"]
            )

            prompt = f"""Analyze this League of Legends game for the player. Be direct, specific, and actionable. No fluff.

RESULT: {stats['result']} in {stats['game_length']}

MY PERFORMANCE ({me['champion']}):
- KDA: {kda}
- CS: {me['cs']} ({stats['cs_per_min']}/min)
- Damage to champions: {me['damage_dealt']:,}
- Damage taken: {me['damage_taken']:,}
- Gold earned: {me['gold']:,}
- Vision score: {me['vision_score']} (wards placed: {me['wards_placed']})
- Level: {me['level']}

MY TEAM:
{teammates}

ENEMY TEAM:
{enemies}

Give me:
1. A one-line verdict on how I played
2. 2-3 specific things I did well (based on the numbers)
3. 2-3 specific things to improve with actionable advice
4. One tip specific to {me['champion']} based on this game

Keep it under 200 words. Talk to me like a coach, not a textbook."""

            response = client.models.generate_content(
                model=RECAP_MODEL,
                contents=prompt,
            )
            text = response.text if response.text else "No analysis generated."

            self._latest_recap = {
                "status": "done",
                "champion": me["champion"],
                "result": stats["result"],
                "kda": kda,
                "cs": me["cs"],
                "cs_per_min": stats["cs_per_min"],
                "damage": me["damage_dealt"],
                "vision": me["vision_score"],
                "gold": me["gold"],
                "analysis": text,
            }
        except Exception as e:
            self._latest_recap = {
                "status": "error",
                "message": str(e),
            }
        finally:
            self._analyzing = False
