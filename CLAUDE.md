# CLAUDE.md / AGENTS.md

Guidance for AI coding agents working in this repository. `AGENTS.md` is a symlink to
this file. The workspace root (`../CLAUDE.md`) owns the cross-repo rules: worktrees,
memory, and the REST contract with the `quality-screener` backend.

## Critical rules

1. **No business logic here.** This is a thin, stateless façade. If a change needs
   computation, it belongs behind a REST endpoint in `quality-screener/`.
   Payload *shaping* (`_slim_score_rows`, `normalize_config`) is the one allowed
   exception — see [Adapters](#adapters).
2. **Branch off `main`** (this repo's default), in a worktree under
   `../worktrees/quality-screener-mcp-server/<branch-slug>/`.
3. **The backend ships first.** Tools talk to the *deployed* API; a tool released ahead
   of its endpoint is broken in production.

## Commands

Requires [`uv`](https://docs.astral.sh/uv/). Python `>=3.11`. No linter or type checker
is configured.

```bash
uv sync                                          # install deps (incl. dev group)
uv run pytest                                    # full suite; no live backend needed
uv run pytest tests/test_tool_filters.py::test_screen_share_builds_full_url
uv run qscreener-mcp                             # stdio transport (default)

# HTTP mode, mirroring the remote deployment:
QSCREENER_MCP_TRANSPORT=streamable-http QSCREENER_MCP_PORT=8080 \
  QSCREENER_API_URL=http://localhost:8001 uv run qscreener-mcp
```

## Architecture

An MCP façade over the Quality Screener REST API (the "stobot" backend), with **no
dependency on the backend Python package** — every tool builds a request and returns the
decoded JSON. Extending it means adding an `@mcp.tool()` that delegates to `_guard`.

Four modules under `qscreener_mcp/`:

- **`server.py`** — the whole tool surface (~760 lines). The `FastMCP` instance, every
  `@mcp.tool()`, token resolution, and the `main()` transport entry point. Config
  (`_API_URL`, `_WEBSITE_URL`, `_PUBLIC_URL`, `_MCP_HOST`) resolves **at import time**
  from env vars, so tests patch the module attribute
  (`monkeypatch.setattr(server, "_WEBSITE_URL", ...)`) rather than the env var.
- **`constants.py`** — everything fixed at build time: header names, env-var names and
  defaults, on-disk filenames, user-facing messages, and the `Tool` enum of canonical
  tool names. Env *values* are deliberately not resolved here.
- **`client.py`** — `ApiClient`, a minimal httpx wrapper. Attaches the bearer token as
  `X-Stobot-CLI-Token`, adds the analytics headers, decodes JSON (`None` for empty
  bodies), raises `ApiError` on any non-2xx. Self-contained copy of the backend CLI's
  client — keep it dependency-free.
- **`oauth.py`** — `StobotOAuthProvider` for HTTP mode. OAuth state is **in-memory**
  (`_pending`, `_codes`) → single-process only. Registered clients persist to
  `~/.config/qscreener/mcp_clients.json`.

### Cross-cutting patterns

**Token resolution (`server._bearer_token`).** Every tool authenticates as the *caller*,
never a shared account. Precedence: HTTP request header (`X-Stobot-CLI-Token`, then
`Authorization: Bearer`) → `$QSCREENER_TOKEN` → `$QSCREENER_CONFIG_DIR/credentials.json`.
The header path reads from `mcp.get_context()` inside a bare `try/except` — there is no
active request in stdio mode.

**The `_guard` wrapper.** Every tool body is a lambda passed to
`_guard(fn, tool=Tool.<NAME>)`. The `tool` keyword is required: call sites hand in
anonymous lambdas, so the name cannot be inferred. `_guard` resolves the token,
short-circuits to `NOT_AUTHENTICATED` if absent, constructs a per-call `ApiClient`, runs
`fn(client)`, and converts `ApiError` into `{"error": str(exc)}`. Tools therefore
**return error dicts, they never raise** — the agent always gets a JSON payload. A `None`
result becomes `{"status": "ok"}`.

**Tool annotations.** Every tool passes `ToolAnnotations`. Read-only tools use the
`_readonly(title)` helper; the handful that write pass their own with the right
`destructiveHint` / `idempotentHint`. All tools set `openWorldHint=True`.

### Auth modes (driven by `QSCREENER_MCP_TRANSPORT`)

- **`stdio`** (default; local agent as a subprocess): token from env var or credentials
  file. No OAuth.
- **`streamable-http`** (remote deploy, e.g. Railway): full MCP OAuth, served at `/mcp`.
  The provider **mints no tokens of its own** — it bridges to the backend's CLI-token
  system. The web app's `/cli-auth` page exchanges the user's session for a CLI token and
  posts it to `/oauth/callback` (`server._oauth_callback` → `oauth.store_auth_code`); that
  **CLI token IS the OAuth access token**. Bearer tokens are validated on *every* request
  via `GET /v1/cli/auth/whoami`. Refresh tokens are unsupported (CLI tokens are long-lived).

## Adapters

Three deliberate exceptions to "no logic", each fixing a real production failure
(see `../memory/decisions/mcp-facade-adapters.md`):

- **`normalize_config()`** reshapes loose `CustomScoreConfig` inputs (snake_case, legacy
  `winsorize`/`zScore` flags, top-level filters) onto the backend contract: weighted metric
  groups → weighted metrics, camelCase params (`winsorizePercentile`,
  `missingDataPercentile`, `normalizeGroupZScores`, `includeDuplicatesInScoring`), and a
  nested `filters` block. Used by `score_compute`, `screen_share`, and the `systems_*`
  tools; see the README example.
- **`_slim_score_rows()`** collapses each row's `duplicates` from full score rows to
  ticker strings and truncates `description` to `DESCRIPTION_LIMIT`. The backend embeds
  full rows for the frontend's expandable rows — ~74% of a ~690 KB payload on a 40-ticker
  call, enough to blow client limits. Pass `full_rows=True` for the raw response.
- **Client headers** `X-Stobot-Client` / `X-Stobot-Client-Op` identify MCP traffic and the
  originating tool to the backend. Analytics metadata only — nothing in auth depends on them.

## Tool conventions

- Tickers are upper-cased before sending (`ticker.upper()`).
- Market-cap parameters are named `*_usd` in tool signatures and mapped to the backend's
  `min_market_cap` / `max_market_cap` by `_filters`. Market caps are always USD.
- `_clean()` drops `None`-valued keys; `_filters()` additionally collapses empty lists to
  `None`, so an unset filter is omitted entirely (omitted filter = unfiltered universe).
  Filter semantics: **OR within a filter, AND across filters.**

## Testing

Tests mock at the seam, never over the network — no live backend required.

| File | Covers |
|---|---|
| `test_tool_filters.py` | Request shaping. Monkeypatches `server._guard` to inject a `_RecordingClient` and asserts on the captured path / params / json. |
| `test_config_normalization.py` | `normalize_config()` input reshaping. |
| `test_slim_rows.py` | `_slim_score_rows()` collapsing and `full_rows=True` passthrough. |
| `test_token_resolution.py` | `_bearer_token()` precedence; fakes `server.mcp.get_context`. |
| `test_client_headers.py` | The analytics headers `ApiClient` attaches. |

When a backend route you consume changes, update the tool, `normalize_config()` if the
request body moved, and the matching test file above.
