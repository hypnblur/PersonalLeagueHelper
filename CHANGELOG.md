# Changelog

## [0.3.0] - draft/pre-game tools & AI provider refactor

### Added
- **AI provider interface** (`src/engine/ai_provider.py`): pluggable AI backends with streaming, timeout, and model fallback.
  - Providers: `gemini` (default, backward compatible), `openai`/`openai_compatible`, `openrouter`, `ollama`/local (OpenAI-compatible HTTP).
  - Config: `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`, `AI_TIMEOUT`, `AI_FALLBACK_MODEL` (legacy `GEMINI_API_KEY`/`RECAP_MODEL` still supported).
- **Draft/pre-game tools** (`src/engine/draft.py`, API + UI):
  - Team comp warnings (estimated AD/AP/mixed damage, frontline/engage, vs-notes).
  - Ban suggestions (role/pool/threat-aware).
  - “What should I play?” (prefers owned champs, good vs locked enemy comp, high global/personal WR, mastery hints).
  - Adaptive build option appended when enemy comp is known (derived from seed situational items; WR not fabricated).
  - **AI Draft Coach** and **AI Build Explain** (uses configured provider, streamed in UI).
- LCU champion mastery list support for mastery-aware recommendations.
- `.env.example`/README updated for AI provider configuration and draft features.

### Changed
- `PostGameAnalyzer` refactored to use the AI provider interface (keeps recap streaming, stats persistence, and fallback behavior).
- `/api/build/...` accepts `enemies` to include adaptive build options.
- Settings runtime reports `ai_provider`/`ai_model`/`ai_configured`.

## [0.2.0] - 2026-05 (personal companion overhaul)

### Added
- **Personal companion persistence (SQLite, `data/companion.db`)**: saved match history/recaps, champ pool, notes/goals, and local settings (`src/data/companion_db.py`).
- **Insights dashboard**: winrate, avg KDA/deaths, CS/min, vision, damage, damage share, per-champion performance, and recent games in the web UI (`/api/insights`, `/api/matches`).
- **Lobby/loading player intel** (best-effort via unofficial LCU): rank, solo/flex winrate (W/L), and picked-champion mastery for participants during champ select/loading phases (`src/engine/intel.py`, `src/lcu/connector.py`, UI panel).
- **Ownership- and performance-aware recommendations**: boosts champs you own (LCU ownership lookup, best-effort), prioritizes good matchups vs locked enemy comp, and factors global WR plus your personal WR from saved matches (`src/engine/recommender.py`, `main.py`).
- **3 build options for the champion you’re playing** (highest WR first): `/api/build/...` returns `build_options`; UI lets you pick an option and import its runes. Current seed provides 1 rated build + 2 transparent situational variants (no fabricated WR) when only one rated build exists (`src/data/store.py`).
- **Packaging/UX**: `pyproject.toml`, `requirements-dev.txt`, `.env.example`, `.gitignore`, updated `README.md`, and one-click `start.bat`.
- **Tests**: `tests/` for store, recommender, rune/shard resolution, and basic Flask API contracts.

### Changed
- **Safer rune import (default on)**: only replaces app-managed rune pages (`LA:*` prefix), adds confirmation/preview flow, and returns clearer LCU error details (`src/lcu/connector.py`, API/UI).
- **Rune resolution hardened**: alias/case-insensitive rune & tree lookup, expanded shard normalization, detailed missing/warning diagnostics, and structural validation helpers (`src/data/dragon.py`).
- **AI post-game recap made faster/more responsive**: streaming output to the dashboard, shorter prompt, capped output config, immediate stats-saved UX, configurable `RECAP_MODEL`, model fallback on model-not-found errors, and timeout/stall handling (`src/engine/postgame.py`, `config.py`, `src/web/static/js/app.js`).
- **Seed build data corrected for current runes**: updated outdated rune names in `data/champions.json` (e.g., `Eyeball Collection`→`Deep Ward`, `Legend: Tenacity`→`Legend: Haste`, `Zombie Ward`→`Deep Ward`, `Phase Rush`→`Stormraider's Surge` per cached Data Dragon naming) so imports resolve.
- **Concurrency/state**: added locking for shared app state and safer monitor-loop handling (`main.py`).

### Fixed
- Rune imports failing due to unresolved/renamed rune names and unclear failure messages.
- Recommendation/rune-import API paths now share app-state context (ownership/personal stats).

### Notes
- LCU features use the **unofficial** local League client API and may break with client updates or be limited by queue/privacy rules.
- Set `GEMINI_API_KEY` in `.env` for AI recaps (optional; match stats are still saved). Use a fast model available to your key via `RECAP_MODEL`.
- `__pycache__` bytecode artifacts are removed from version control and ignored going forward.