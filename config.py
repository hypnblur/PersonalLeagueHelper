import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Optional .env support (personal use convenience)
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except Exception:
    pass

RIOT_DDRAGON = "https://ddragon.leagueoflegends.com"

LCU_POLL_INTERVAL = int(os.environ.get("LCU_POLL_INTERVAL", "2"))
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

LEAGUE_INSTALL_PATHS = [
    r"C:\Riot Games\League of Legends",
    r"D:\Riot Games\League of Legends",
    r"C:\Program Files\Riot Games\League of Legends",
    r"C:\Program Files (x86)\Riot Games\League of Legends",
]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Use the fastest model available to your key (Flash/Flash-Lite). Override in .env.
RECAP_MODEL = os.environ.get("RECAP_MODEL", "gemini-2.0-flash")
DB_PATH = os.environ.get("COMPANION_DB_PATH", os.path.join(DATA_DIR, "companion.db"))
OPEN_BROWSER = os.environ.get("OPEN_BROWSER", "1").lower() in ("1", "true", "yes")
SAFE_RUNE_IMPORT = os.environ.get("SAFE_RUNE_IMPORT", "1").lower() in ("1", "true", "yes")
RUNE_PAGE_PREFIX = os.environ.get("RUNE_PAGE_PREFIX", "LA:")
