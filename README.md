# League Advisor — Personal Companion

A local, personal League of Legends companion app. It runs a small Flask dashboard on your machine and can:
- Show champion pick recommendations from your local champion/build dataset
- Detect champ select/loading via the League Client (LCU) when the client is running
- Show best-effort lobby/loading intel (rank, winrate, picked-champion mastery) when exposed by the client
- Recommend champs based on **owned champions, locked enemy comp, and high winrate** (global + your personal history)
- Display **3 build options** for the champion you’re playing (highest WR first) and import the selected rune page (safe mode by default)
- Capture post-game stats and generate an optional AI recap (Gemini, streamed for faster response)
- Save match history locally and show personal insights (winrate, KDA, deaths, CS/min, vision, damage share, per-champion)
- Keep a champion pool and personal notes/goals

> **Note:** LCU integration uses unofficial local client endpoints and may break with League client updates or be limited by queue/privacy rules. Use for personal purposes and follow Riot’s applicable policies/terms. Rune import in safe mode only manages pages with the app prefix (default `LA:`).

## Setup

```powershell
cd C:\Users\machine2\Documents\LeagueAPP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` and set `GEMINI_API_KEY` for AI recaps.

## Run

```powershell
python main.py
```

Or double-click `start.bat` (after first-time setup).

Useful options:

```powershell
python main.py --no-browser      # don't auto-open dashboard
python main.py --no-lcu          # UI/data development without League client polling
python main.py --host 127.0.0.1 --port 8080
```

Dashboard: `http://127.0.0.1:8080`

## Configuration

Environment variables / `.env`:
- `GEMINI_API_KEY` — enables AI recap (optional; stats are still saved)
- `RECAP_MODEL` — Gemini model ID (default: `gemini-2.0-flash`; set to the fastest model available to your key)
- `WEB_HOST`, `WEB_PORT`
- `OPEN_BROWSER` (`1`/`0`)
- `SAFE_RUNE_IMPORT` (`1`/`0`) — when enabled, import only replaces app-owned rune pages
- `RUNE_PAGE_PREFIX` — default `LA:`
- `LCU_POLL_INTERVAL`

## Data

- `data/champions.json` — local seed for builds/counters/synergies/tiers (update periodically for accuracy)
- `cache/` — Data Dragon cache
- `data/companion.db` — local SQLite history, insights, champ pool, notes, settings (personal data)

## Tests

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## Project layout

- `main.py` — app bootstrap, LCU monitor loop
- `config.py` — configuration
- `src/lcu/connector.py` — League Client local API connector
- `src/data/dragon.py` — Data Dragon fetch/cache + rune resolution
- `src/data/store.py` — champion/build data access
- `src/data/companion_db.py` — local SQLite persistence
- `src/engine/recommender.py` — pick recommendations
- `src/engine/intel.py` — lobby/loading player intel (rank/winrate/mastery)
- `src/engine/postgame.py` — post-game stats + optional AI recap
- `src/web/server.py` — Flask API/routes
- `src/web/templates/index.html`, `src/web/static/*` — dashboard UI

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md).