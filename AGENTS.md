# WYDT - Agent Notes

## Commands

```bash
uv run wydt serve              # Dev server (default port 5000, debug on)
uv run wydt create "text"      # Create entry (auto-generates summary)
uv run wydt list               # List recent entries
uv run wydt search "query"     # Search entries
uv run wydt get 2026-03-05     # Get specific entry
uv run wydt init-db            # Init DB (safe to re-run)
uv run ruff check src/         # Lint
```

`flask --app wydt run` also works.

## Architecture

- **Flask app factory**: `src/wydt/__init__.py:create_app()` — all routes defined inline
- **CLI**: `src/wydt/cli.py` — Click-based, entrypoint `wydt`
- **Models**: `src/wydt/models.py` — `DailyLog`, `WeeklySummary` (SQLAlchemy + SQLite)
- **LLM**: `src/wydt/llm.py` — OpenAI-compatible, env-configurable
- **MCP**: `src/wydt/mcp.py` — stdin/stdout and HTTP `/mcp` endpoint
- **Templates**: `src/wydt/templates/` — HTML + HTMX + Bootstrap 5

## HTMX Partial Pattern

HTMX requests (`HX-Request` header) must return **partial templates**, not full page templates. Full templates rendered into a `hx-target` element cause nested DOM duplication.

Convention:
- Full page templates: `name.html` (e.g. `entry.html`, `weekly.html`)
- HTMX swap targets: `name_partial.html` (e.g. `entry_partial.html`, `logs_partial.html`, `weekly_summary_partial.html`)

The `entry` route (`__init__.py:69`) demonstrates this — POST with HTMX returns `entry_partial.html`, not `entry.html`.

## Env Loading

- `.env` loaded by `cli.py` via `python-dotenv` (line 50)
- Flask `__init__.py` does **not** load `.env` — relies on env vars being set externally
- Key vars: `WYDT_PASSWORD`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `DATABASE_URL`

## Toolchain

- Package manager: `uv` (lockfile: `uv.lock`, builder: `uv_build`)
- Python: 3.14 (`.python-version`)
- Linter: `ruff`
- No tests exist yet

## Deployment

Runs as a systemd user service: `systemctl --user {start,stop,restart,status} wydt.service`
