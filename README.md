# WYDT - What You Did Today

A personal daily journal/tracker webapp with LLM integration.

## Commands
systemctl --user start wydt.service   # Start
systemctl --user stop wydt.service    # Stop
systemctl --user restart wydt.service # Restart
systemctl --user status wydt.service # Check status
journalctl --user-unit=wydt.service   # View logs

## Note
This is vibe coded, I haven't read the code.
It might be insecure, it might even kick your dog.
It's mildly useful for me, but use at your own risk.
Contributions welcome!

## Features

- **Daily Logging** - Record what you did each day
- **Searchable** - Search by keywords or filter by date
- **Auto-Summary** - AI generates a short summary of each day
- **Editable Prompts** - Tune the daily and weekly prompts from the UI (stored in the database)
- **REST API** - Access your data via JSON endpoints
- **MCP Server** - Claude Desktop integration via Model Context Protocol
- **Authentication** - Basic auth for web UI and API access

## Tech Stack

- Backend: Flask + SQLAlchemy + SQLite
- Frontend: HTML + HTMX + Bootstrap 5
- LLM: OpenAI-compatible API (configurable)

## Installation

```bash
# Install dependencies
pip install -e .

# Or with uv
uv pip install -e .
```

## Configuration

Create a `.env` file:

```bash
# Authentication (optional - if not set, no auth required)
WYDT_PASSWORD=your_password

# LLM Configuration (uses the OpenCode inference API by default)
OPENCODE_API_KEY=your_opencode_console_key_here

# Pay-as-you-go OpenCode Models (needs Console credits)
# LLM_BASE_URL=https://opencode.ai/inference/v1

# Or bill to an OpenCode Go subscription instead of credits
LLM_BASE_URL=https://opencode.ai/inference/go/v1

# LLM_MODEL=gpt-5-nano   # Optional. Leave unset (recommended) to auto-select
                       # the cheapest available model via /v1/models. Selection
                       # uses the pricing in the model list, skipping free-tier
                       # models and models that train on your requests.
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WYDT_PASSWORD` | Password for auth (if set) | None (no auth) |
| `OPENCODE_API_KEY` | OpenCode Console API key for [`https://opencode.ai/inference/v1`](https://opencode.ai/docs/console/models) | None |
| `LLM_API_KEY` | Fallback API key if `OPENCODE_API_KEY` is unset | Uses `OPENAI_API_KEY` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint | `https://opencode.ai/inference/v1` |
| `LLM_MODEL` | Specific model to use. **Leave unset** to let the app automatically query `/v1/models` and pick the cheapest model your key can use, ranked by real input+output pricing (free-tier models are skipped; set `LLM_ALLOW_FREE_MODELS=1` to include them). | Auto-discovered (`gpt-5-nano` fallback) |
| `LLM_REASONING_EFFORT` | Force a reasoning effort (e.g. `low`, `minimal`) or `none`/`off` to disable. Only auto-applied for auto-discovered models. | `low` when the model supports it |
| `LLM_ALLOW_FREE_MODELS` | Include free-tier models in auto-discovery. They normally only serve OpenCode itself, so they may be rejected. | Unset (skip them) |
| `LLM_ALLOW_TRAINING_MODELS` | Include contributor/free tiers that train on your requests. Off by default since journal entries are private. | Unset (skip them) |
| `LLM_SESSION_ID` | Session ID sent as `x-opencode-session` (required by the Go provider; helps routing/prompt caching). | Random UUID per process |
| `LLM_USER_AGENT` | User agent sent with requests | `wydt/0.1.0` |

### OpenCode Go vs OpenCode Models

Two OpenCode endpoints work, both OpenAI-compatible:

- `https://opencode.ai/inference/v1` — pay-as-you-go, billed to your Console credit balance. Requests fail with `402 Insufficient balance` when the balance is empty.
- `https://opencode.ai/inference/go/v1` — billed against an OpenCode Go subscription instead of credits. It requires a stable `x-opencode-session` header, which wydt sends automatically.

Go is intended for coding-agent traffic; see [Where can I use it?](https://opencode.ai/docs/console/go#where-can-i-use-it) before putting a non-coding workload on it.
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///wydt.db` |

## Running

```bash
# Development
flask --app wydt run

# Or use the CLI
wydt
```

The app runs at `http://localhost:5000`.

## Usage

1. Open `http://localhost:5000`
2. If password is set, enter it in the browser prompt
3. Click "New Entry" or today's date to add what you did
4. The entry saves automatically and generates an AI summary
5. Use the search bar to find entries by keyword
6. Use the date picker to filter by specific date

### Prompts

Click **Prompt** on the main screen to edit the prompts wydt sends to the model:

| Prompt | Sent as | Placeholders |
|--------|---------|--------------|
| Daily summary - system message | system | - |
| Daily summary - user message | user | `{content}` |
| Weekly summary - system message | system | - |
| Weekly summary - user message | user | `{logs}` |
| Weekly summary - one day's entry | inside `{logs}` | `{date}`, `{summary}`, `{content}` |

They live in the `prompts` table, are applied to the next summary you generate,
and each can be restored to its default with **Reset**. On first run the table is
populated with the defaults in `DEFAULT_PROMPTS` (`src/wydt/models.py`), which
are otherwise only used as a fallback when a prompt is cleared or no database is
available. Each daily log is still truncated to 500 characters before it goes
into a weekly summary.

## API

All API endpoints require Basic Auth. Use the `WYDT_PASSWORD` as the password.

### List Logs
```
GET /api/logs
GET /api/logs?q=<keyword>
GET /api/logs?date=<YYYY-MM-DD>
```

### Single Entry
```
GET /api/logs/<date>
POST /api/logs
```

Example:
```bash
# Search entries
curl -u "user:your_password" "http://localhost:5000/api/logs?q=meeting"

# Get specific date
curl -u "user:your_password" "http://localhost:5000/api/logs/2026-03-05"

# Create entry
curl -u "user:your_password" -X POST http://localhost:5000/api/logs \
  -H "Content-Type: application/json" \
  -d '{"content": "Working on the WYDT project"}'
```

## MCP Integration

MCP can be used in two ways:

### Local (stdin/stdout)
For Claude Desktop running on the same machine:

```json
{
  "mcpServers": {
    "wydt": {
      "command": "python",
      "args": ["-m", "wydt.mcp"],
      "env": {
        "WYDT_PASSWORD": "your_password",
        "OPENCODE_API_KEY": "your_opencode_console_key",
        "LLM_BASE_URL": "https://opencode.ai/inference/v1"
      }
    }
  }
}
```

### Remote (HTTP)
For external LLM tools or Claude Code CLI:

### HTTP MCP Endpoint

For remote access (other machines), use the HTTP endpoint:

```bash
# Initialize
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# List tools
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'

# Get logs
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_logs", "arguments": {"limit": 10}}}'
```

For remote use, add Basic Auth: `curl -u "user:password" ...`

## Development

```bash
# Run tests (if any)
pytest

# Lint
ruff check src/
```
