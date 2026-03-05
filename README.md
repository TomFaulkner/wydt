# WYDT - What You Did Today

A personal daily journal/tracker webapp with LLM integration.

## Note
This is vibe coded, I haven't read the code.
It might be insecure, it might even kick your dog.
It's mildly useful for me, but use at your own risk.
Contributions welcome!

## Features

- **Daily Logging** - Record what you did each day
- **Searchable** - Search by keywords or filter by date
- **Auto-Summary** - AI generates a short summary of each day
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

# LLM Configuration (uses OpenAI by default)
OPENAI_API_KEY=your_api_key_here

# Or use a different OpenAI-compatible endpoint (e.g., xAI Grok)
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-beta
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WYDT_PASSWORD` | Password for auth (if set) | None (no auth) |
| `OPENAI_API_KEY` | OpenAI API key | None |
| `LLM_API_KEY` | Override API key for LLM | Uses `OPENAI_API_KEY` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint | None (uses OpenAI) |
| `LLM_MODEL` | Model to use for summaries | `gpt-4o-mini` |
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
        "LLM_API_KEY": "your_api_key",
        "LLM_BASE_URL": "https://api.x.ai/v1",
        "LLM_MODEL": "grok-beta"
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
