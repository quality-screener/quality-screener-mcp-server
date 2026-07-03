# Quality Screener MCP server

A standalone [Model Context Protocol](https://modelcontextprotocol.io) (MCP)
server that exposes the [Quality Screener](https://qualityscreener.io)
stock-screening engine as tools for AI agents (Claude, Cursor, and any other MCP
client).

Once connected, an agent can screen and filter the scored universe, compute
custom quality scores, inspect score history, manage saved scoring systems, and
generate shareable screen links — **acting as the signed-in user**, against the
same data they see in the web dashboard.

- **No SDK dependency.** The server is a thin HTTP layer over the public
  Quality Screener API. It has **no dependency on the backend Python package** —
  every tool just calls a REST endpoint and returns the JSON payload.
- **Multi-tenant & credential-free.** When deployed over HTTP the server stores
  no credentials of its own. Each request carries the caller's own access token,
  which the server forwards to the API, so a single public deployment can serve
  many users without ever acting on a shared account.

---

## Table of contents

- [How it works](#how-it-works)
- [Quick start (remote)](#quick-start-remote)
- [Running locally](#running-locally)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [Tools](#tools)
- [Working with `CustomScoreConfig`](#working-with-customscoreconfig)
- [Connecting an MCP client](#connecting-an-mcp-client)
- [Deployment](#deployment)
- [Development](#development)
- [License](#license)

---

## How it works

```
┌─────────────┐   MCP (stdio | streamable-HTTP)   ┌──────────────────┐   HTTPS   ┌──────────────────────┐
│  AI agent   │ ────────────────────────────────► │  qscreener-mcp   │ ────────► │ Quality Screener API │
│ (MCP client)│ ◄──────────────────────────────── │   (this server)  │ ◄──────── │   (FastAPI backend)  │
└─────────────┘         tool calls / JSON          └──────────────────┘  REST     └──────────────────────┘
```

Each MCP tool maps to one Quality Screener REST endpoint. The server attaches
the caller's bearer token to every outbound request (header
`X-Stobot-CLI-Token`, `Authorization: Bearer …` also accepted) and returns the
decoded JSON. There is no business logic in the server itself — it is a typed,
authenticated façade over the API.

It runs in two transport modes:

| Transport | Use | Authentication |
| --- | --- | --- |
| `stdio` (default) | A local agent (e.g. Claude Code) launches the server as a subprocess | Token from `$QSCREENER_TOKEN` or `~/.config/qscreener/credentials.json` |
| `streamable-http` | A remote, externally reachable deployment (e.g. Railway) | End-to-end MCP **OAuth 2.0** — the client opens the browser once, then sends the token automatically; or a per-request `X-Stobot-CLI-Token` header |

Over HTTP the MCP endpoint is served at `/mcp`.

---

## Quick start (remote)

The easiest way to use the server is to point your MCP client at the hosted
deployment. No token to copy — the client triggers a browser sign-in on first
connect:

```json
{
  "mcpServers": {
    "qscreener": {
      "type": "streamable-http",
      "url": "https://mcp.qualityscreener.io/mcp"
    }
  }
}
```

On first use your browser opens the Quality Screener sign-in page. Approve once,
and the agent stays connected. You need a Quality Screener account; the agent
inherits exactly your access.

---

## Running locally

Requires [`uv`](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# stdio — for a local agent that launches this as a subprocess
uv run qscreener-mcp

# streamable-HTTP — mirrors the remote deployment
QSCREENER_MCP_TRANSPORT=streamable-http QSCREENER_MCP_PORT=8080 \
  QSCREENER_API_URL=http://localhost:8001 \
  uv run qscreener-mcp
# -> MCP endpoint at http://localhost:8080/mcp
```

With Docker:

```bash
docker build -t qscreener-mcp .
docker run --rm -p 8080:8080 \
  -e QSCREENER_API_URL=https://your-backend.example.com \
  -e QSCREENER_MCP_PUBLIC_URL=http://localhost:8080 \
  qscreener-mcp
# -> MCP endpoint at http://localhost:8080/mcp
```

By default the container runs the `streamable-http` transport on port `8080`.

---

## Configuration

All configuration is via environment variables, resolved at startup.

| Env var | Default | Meaning |
| --- | --- | --- |
| `QSCREENER_API_URL` | `http://localhost:8001` | Base URL of the Quality Screener backend API the tools call |
| `QSCREENER_MCP_TRANSPORT` | `stdio` | `stdio`, `streamable-http`, or `sse` |
| `QSCREENER_WEBSITE_URL` | `http://localhost:3001` | Web-app base URL used to build the OAuth browser-login link and shareable screen URLs |
| `QSCREENER_MCP_PUBLIC_URL` | `http://localhost:{PORT\|8080}` | Publicly reachable base URL of this server; used to build the OAuth callback URL |
| `PORT` | — | Bind port for HTTP transports (Railway sets this automatically) |
| `QSCREENER_MCP_PORT` | `8080` | Bind port fallback when `PORT` is unset |
| `QSCREENER_MCP_HOST` | `0.0.0.0` | Bind host for HTTP transports |
| `QSCREENER_TOKEN` | — | Bearer-token override for stdio mode (single user) |
| `QSCREENER_CONFIG_DIR` | `~/.config/qscreener` | Directory holding `credentials.json` for stdio mode |

---

## Authentication

The server resolves a bearer token for each call with the following precedence:

1. **HTTP request header** — `X-Stobot-CLI-Token`, then `Authorization: Bearer <token>`.
2. **`$QSCREENER_TOKEN`** environment variable.
3. **`$QSCREENER_CONFIG_DIR/credentials.json`** — the `token` field.

### Remote (OAuth 2.0)

For a `streamable-http` deployment, authentication is fully automated via the
MCP OAuth flow:

1. The MCP client discovers the authorization server and opens the user's browser.
2. The browser lands on the Quality Screener web app, which exchanges the user's
   web session for a short-lived CLI token and redirects back to this server's
   `/oauth/callback`.
3. The server hands the token to the MCP client, which sends it as a bearer token
   on every subsequent request.

The token is validated on each request by calling the backend's
`/v1/cli/auth/whoami` endpoint, so a revoked or expired token is rejected
immediately. The server never persists user tokens.

### Local (stdio)

Mint a token through the browser login flow and store it locally, then run the
server over stdio:

```bash
qscreener auth login                          # opens the web app, stores a token
cat ~/.config/qscreener/credentials.json      # the "token" field is your bearer token
```

Or set `QSCREENER_TOKEN` directly for CI / scripted use.

---

## Tools

All tools require authentication. Filters use **OR logic within a filter** and
**AND logic across filters**. Market caps are always in **USD**.

### Account & status

| Tool | Signature | Description |
| --- | --- | --- |
| `auth_status` | `auth_status()` | Whether a token is present and which user it authenticates as. |
| `account_profile` | `account_profile()` | The signed-in user's profile (email, username, organization). |
| `health` | `health()` | API and database health check. |

### Scores & screening

| Tool | Signature | Description |
| --- | --- | --- |
| `scores_top` | `scores_top(limit=20)` | Top tickers by quality score, as a `{ticker: score}` map. |
| `scores_list` | `scores_list(ticker=None, sectors=None, industries=None, countries=None, currencies=None, exchanges=None, min_score=None, max_score=None, min_market_cap_usd=None, max_market_cap_usd=None, sort_by="quality_score", sort_order="desc", offset=0, limit=50, include_duplicates=False)` | List scored tickers with optional filters. |
| `scores_show` | `scores_show(ticker)` | Full score row(s) for a single ticker. |
| `scores_statistics` | `scores_statistics(sectors=None, min_score=None, max_score=None, min_market_cap_usd=None, max_market_cap_usd=None)` | Min / max / average score statistics for a filtered universe. |
| `scores_market_cap` | `scores_market_cap(sectors=None, min_score=None)` | Aggregated total market cap (USD) for a filtered universe. |
| `score_compute` | `score_compute(config, sectors=None, industries=None, countries=None, currencies=None, exchanges=None, min_market_cap_usd=None, max_market_cap_usd=None, sort_by="quality_score", sort_order="desc", offset=0, limit=50, include_duplicates=False)` | Compute custom scores from a `CustomScoreConfig`, restricted to a filtered universe. |

### Sharing

| Tool | Signature | Description |
| --- | --- | --- |
| `screen_share` | `screen_share(config)` | Persist a `CustomScoreConfig` and return a public, copy-pasteable share link (`url`, `slug`, `created`, `view_count`). Content-addressed: an identical config returns the same link. |

### Filters & tickers

| Tool | Signature | Description |
| --- | --- | --- |
| `filters_list` | `filters_list()` | Available filter values (sectors, industries, countries, currencies, exchanges). |
| `tickers_list` | `tickers_list(limit=None)` | Available tickers, optionally truncated to `limit`. |
| `tickers_search` | `tickers_search(query)` | Search available tickers by case-insensitive substring. |

### Score history

Dates are `YYYY-MM-DD`. Pass `scoring_system_id` to compute history against a
saved scoring system instead of the default quality score.

| Tool | Signature | Description |
| --- | --- | --- |
| `history_ticker` | `history_ticker(ticker, start=None, end=None, scoring_system_id=None)` | Score history for a single ticker over a date range. |
| `history_batch` | `history_batch(tickers, start=None, end=None, scoring_system_id=None)` | Score history for several tickers at once. |
| `history_top` | `history_top(top=10, scoring_system_id=None)` | Fetch the current top-N tickers and return their score history. |

### Saved scoring systems

A scoring system is a named, reusable `CustomScoreConfig` stored against your
account.

| Tool | Signature | Description |
| --- | --- | --- |
| `systems_list` | `systems_list()` | List your saved scoring systems. |
| `systems_show` | `systems_show(system_id)` | Show a saved scoring system by ID. |
| `systems_create` | `systems_create(name, config, description=None)` | Create a saved scoring system from a config object. |
| `systems_update` | `systems_update(system_id, name=None, config=None, description=None)` | Update a saved scoring system. |
| `systems_delete` | `systems_delete(system_id)` | Delete a saved scoring system. |
| `systems_apply` | `systems_apply(system_id)` | Apply a saved scoring system (increments its usage count). |

---

## Working with `CustomScoreConfig`

`score_compute`, `screen_share`, and the `systems_*` tools accept a
`CustomScoreConfig` object describing how to weight financial metrics. Its shape
mirrors the score builder in the web dashboard: weighted metric **groups**, each
containing weighted **metrics**, plus statistical options. A minimal example:

```json
{
  "name": "My quality screen",
  "groups": [
    {
      "id": "returns",
      "name": "Returns",
      "weight": 0.5,
      "metrics": [
        { "id": "roe", "name": "ROE", "weight": 0.5 },
        { "id": "roic", "name": "ROIC", "weight": 0.5 }
      ]
    },
    {
      "id": "profitability",
      "name": "Profitability",
      "weight": 0.5,
      "metrics": [
        { "id": "profit_margin", "name": "Profit Margin", "weight": 1.0 }
      ]
    }
  ],
  "winsorize": true,
  "zScore": true
}
```

Use `filters_list` to discover valid filter values, and build a config
interactively in the dashboard if you want a starting point to copy.

---

## Connecting an MCP client

### Remote (recommended)

Any `streamable-http` MCP client works. No token needed — OAuth handles login:

```json
{
  "mcpServers": {
    "qscreener": {
      "type": "streamable-http",
      "url": "https://mcp.qualityscreener.io/mcp"
    }
  }
}
```

If your client cannot perform the OAuth flow, send a minted token directly:

```json
{
  "mcpServers": {
    "qscreener": {
      "url": "https://mcp.qualityscreener.io/mcp",
      "headers": { "X-Stobot-CLI-Token": "<your token>" }
    }
  }
}
```

### Local (stdio)

```json
{
  "mcpServers": {
    "qscreener": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/quality-screener-mcp-server", "qscreener-mcp"],
      "env": { "QSCREENER_API_URL": "https://your-backend.example.com" }
    }
  }
}
```

---

## Deployment

The server deploys as a single container. On [Railway](https://railway.app):

1. **New service → Deploy from repo**, pointing at this repository. The
   Dockerfile is self-contained, so the build context is the repo root.
2. Set environment variables:
   - `QSCREENER_MCP_TRANSPORT=streamable-http`
   - `QSCREENER_API_URL=https://<your-backend-domain>`
   - `QSCREENER_WEBSITE_URL=https://<your-frontend-domain>`
   - `QSCREENER_MCP_PUBLIC_URL=https://<generated-mcp-domain>`

   Railway injects `PORT` automatically; the server binds to it.
3. **Networking → Generate Domain.** The MCP endpoint is
   `https://<generated-domain>/mcp`.
   - Leave the HTTP healthcheck path unset (or use a TCP check): `/mcp` answers
     `406 Not Acceptable` to a plain `GET`, so an HTTP healthcheck expecting
     `200` would mark the deploy unhealthy.
4. **Connect** your MCP client — the OAuth flow triggers automatically on first
   connection.

---

## Development

```bash
uv sync            # install dependencies (including dev)
uv run pytest      # run the test suite
```

The codebase is small and self-contained:

| Path | Purpose |
| --- | --- |
| `qscreener_mcp/server.py` | FastMCP server, tool definitions, transport entry point |
| `qscreener_mcp/client.py` | Minimal httpx client that attaches the bearer token |
| `qscreener_mcp/oauth.py` | MCP OAuth 2.0 provider (token validation, browser flow) |
| `tests/` | pytest suite (token resolution, filter forwarding, share-link building) |

---

## License

[MIT](LICENSE) © Quality Screener.
