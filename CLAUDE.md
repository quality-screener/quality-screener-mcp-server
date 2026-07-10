# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Requires [`uv`](https://docs.astral.sh/uv/). There is no configured linter or type checker.

```bash
uv sync                                          # install deps (incl. dev group)
uv run pytest                                    # run the full test suite
uv run pytest tests/test_tool_filters.py         # run one test file
uv run pytest tests/test_tool_filters.py::test_screen_share_builds_full_url  # run one test
uv run qscreener-mcp                             # run the server (stdio transport, default)

# run over HTTP, mirroring the remote deployment:
QSCREENER_MCP_TRANSPORT=streamable-http QSCREENER_MCP_PORT=8080 \
  QSCREENER_API_URL=http://localhost:8001 uv run qscreener-mcp
```

## Architecture

This is a **thin, stateless MCP façade over the Quality Screener REST API** (the "stobot" backend). It has **no dependency on the backend Python package** — every tool just calls a REST endpoint and returns the decoded JSON. There is deliberately **no business logic here**; resist adding any. When extending, the pattern is: add an `@mcp.tool()` that builds a request and delegates to `_guard`.

Three modules under `qscreener_mcp/`:

- **`server.py`** — the whole surface. Defines the `FastMCP` instance, every `@mcp.tool()`, token resolution, and the `main()` transport entry point. Config (`_API_URL`, `_WEBSITE_URL`, `_PUBLIC_URL`, `_MCP_HOST`) is resolved **at import time** from env vars, so tests that depend on it use `monkeypatch.setattr(server, "_WEBSITE_URL", ...)` rather than setting the env var.
- **`client.py`** — `ApiClient`, a minimal httpx wrapper. Attaches the bearer token as the `X-Stobot-CLI-Token` header, decodes JSON (or `None` for empty bodies), and raises `ApiError` on any non-2xx. Self-contained copy of the backend CLI's client — keep it dependency-free.
- **`oauth.py`** — `StobotOAuthProvider`, the MCP OAuth 2.0 provider for HTTP mode. All OAuth state is **in-memory** (`_pending`, `_codes`) → single-process only. Registered clients persist to `~/.config/qscreener/mcp_clients.json`.

### Two key cross-cutting patterns

**Token resolution (`server._bearer_token`).** Every tool authenticates as the *caller*, never a shared account. Precedence: HTTP request header (`X-Stobot-CLI-Token`, then `Authorization: Bearer`) → `$QSCREENER_TOKEN` → `$QSCREENER_CONFIG_DIR/credentials.json`. The header path reads from `mcp.get_context()` and is wrapped in a bare `try/except` because there is no active request in stdio mode.

**The `_guard` wrapper.** Every tool body is a lambda passed to `_guard(fn)`. `_guard` resolves the token, short-circuits to a `{"error": ...}` dict if absent, constructs a per-call `ApiClient`, runs `fn(client)`, and converts `ApiError` into `{"error": str(exc)}`. Tools therefore **return error dicts, they do not raise** — the agent always gets a JSON payload. A `None` result becomes `{"status": "ok"}`.

### The two auth modes (driven by `QSCREENER_MCP_TRANSPORT`)

- **`stdio`** (default, local agent as subprocess): token comes from env var or credentials file. No OAuth.
- **`streamable-http`** (remote deploy, e.g. Railway): full MCP OAuth. The OAuth provider does **not mint its own tokens** — it bridges to the backend's existing CLI-token system. The web app's `/cli-auth` page exchanges the user's session for a CLI token, posts it back to this server's `/oauth/callback` route (`server._oauth_callback` → `oauth.store_auth_code`), and that **CLI token IS returned as the OAuth access token**. Bearer tokens are validated on *every* request via the backend `GET /v1/cli/auth/whoami`. Refresh tokens are unsupported (CLI tokens are long-lived). MCP is served at `/mcp`.

## Conventions for tools

- Tickers are upper-cased before sending (`ticker.upper()`).
- Market-cap parameters are named `*_usd` in the tool signature and mapped to the backend's `min_market_cap`/`max_market_cap` by `_filters`. Market caps are always USD.
- `_clean()` drops `None`-valued keys; `_filters()` additionally collapses empty lists to `None` so unset filters are omitted entirely (an omitted filter = unfiltered universe). Filter semantics: **OR within a filter, AND across filters.**
- `score_compute`, `screen_share`, and the `systems_*` tools take a `CustomScoreConfig` dict (weighted metric groups → weighted metrics, plus camelCase scoring parameters `winsorizePercentile`/`missingDataPercentile`/`normalizeGroupZScores`/`includeDuplicatesInScoring` and a nested `filters` block); see the README example. `normalize_config()` reshapes loose inputs (snake_case, legacy `winsorize`/`zScore` flags, top-level filters) onto this contract before the request is sent.

## Testing

Tests mock at the seam, not over the network. `test_tool_filters.py` monkeypatches `server._guard` to inject a `_RecordingClient` and asserts on the captured request (path / params / json). `test_token_resolution.py` monkeypatches `server.mcp.get_context` with a fake context to drive `_bearer_token`'s precedence logic. No live backend is needed.
