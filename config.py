import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DATA_DIR = os.path.join(BASE_DIR, "data")

RIOT_DDRAGON = "https://ddragon.leagueoflegends.com"

LCU_POLL_INTERVAL = 2
WEB_HOST = "127.0.0.1"
WEB_PORT = 8080

LEAGUE_INSTALL_PATHS = [
    r"C:\Riot Games\League of Legends",
    r"D:\Riot Games\League of Legends",
    r"C:\Program Files\Riot Games\League of Legends",
    r"C:\Program Files (x86)\Riot Games\League of Legends",
]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
RECAP_MODEL = "gemini-3.5-flash"
