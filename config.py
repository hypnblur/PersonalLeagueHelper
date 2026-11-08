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

# AI provider config (backward compatible with GEMINI_API_KEY / RECAP_MODEL)
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()  # gemini | openai | openai_compatible | ollama
AI_API_KEY = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL") or os.environ.get("RECAP_MODEL") or "gemini-3.8-flash"
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").strip().rstrip("/")
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "60"))
AI_FALLBACK_MODEL = os.environ.get("AI_FALLBACK_MODEL", "").strip()

# Legacy aliases (kept for compatibility)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or (AI_API_KEY if AI_PROVIDER == "gemini" else "")
RECAP_MODEL = AI_MODEL
DB_PATH = os.environ.get("COMPANION_DB_PATH", os.path.join(DATA_DIR, "companion.db"))
OPEN_BROWSER = os.environ.get("OPEN_BROWSER", "1").lower() in ("1", "true", "yes")
SAFE_RUNE_IMPORT = os.environ.get("SAFE_RUNE_IMPORT", "1").lower() in ("1", "true", "yes")
RUNE_PAGE_PREFIX = os.environ.get("RUNE_PAGE_PREFIX", "LA:")
