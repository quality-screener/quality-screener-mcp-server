"""Standalone MCP server exposing qscreener operations as tools.

Runs in two transport modes, selected by ``QSCREENER_MCP_TRANSPORT``:

* ``stdio`` (default) — for a local agent (e.g. Claude Code) launching the
  server as a subprocess.  The bearer token is read from ``$QSCREENER_TOKEN``
  or ``~/.config/qscreener/credentials.json`` (written by
  ``qscreener auth login``).

* ``streamable-http`` — for remote deployments (e.g. Railway).  Authentication
  is handled end-to-end via MCP OAuth 2.0: the MCP client discovers the
  authorization server, opens the user's browser once, and thereafter sends
  ``Authorization: Bearer <cli-token>`` automatically.  No manual token
  copy-paste required.

Environment variables
---------------------
QSCREENER_API_URL         Backend API base URL (default http://localhost:8001)
QSCREENER_WEBSITE_URL     Web-app base URL for the OAuth browser redirect
                          (default http://localhost:3001)
QSCREENER_MCP_PUBLIC_URL  Publicly reachable base URL of this MCP server;
                          used to build the OAuth callback URL
                          (default http://localhost:{PORT|QSCREENER_MCP_PORT|8080})
QSCREENER_TOKEN           Bearer-token override for stdio mode (optional)
QSCREENER_MCP_TRANSPORT   stdio | streamable-http | sse  (default stdio)
PORT / QSCREENER_MCP_PORT Bind port for HTTP transports (Railway sets PORT)
QSCREENER_MCP_HOST        Bind host for HTTP transports (default 0.0.0.0)
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from qscreener_mcp.client import ApiClient, ApiError
from qscreener_mcp.oauth import StobotOAuthProvider, store_auth_code

# ------------------------------------------------------------------ #
# Configuration — resolved at import time from environment variables  #
# ------------------------------------------------------------------ #

_API_URL: str = os.environ.get("QSCREENER_API_URL", "http://localhost:8001").rstrip("/")
_WEBSITE_URL: str = os.environ.get("QSCREENER_WEBSITE_URL", "http://localhost:3001").rstrip("/")
# Resolve bind host early so FastMCP's constructor sees the real value and does not
# auto-enable localhost-only DNS rebinding protection when we are binding to 0.0.0.0.
_MCP_HOST: str = os.environ.get("QSCREENER_MCP_HOST", "0.0.0.0")


def _public_url() -> str:
    port = os.environ.get("PORT") or os.environ.get("QSCREENER_MCP_PORT") or "8080"
    return os.environ.get("QSCREENER_MCP_PUBLIC_URL", f"http://localhost:{port}").rstrip("/")


_PUBLIC_URL: str = _public_url()

# ------------------------------------------------------------------ #
# OAuth provider + FastMCP instance                                   #
# ------------------------------------------------------------------ #

_oauth = StobotOAuthProvider(
    api_url=_API_URL,
    website_url=_WEBSITE_URL,
    mcp_public_url=_PUBLIC_URL,
)

mcp = FastMCP(
    "qscreener",
    host=_MCP_HOST,
    auth_server_provider=_oauth,
    auth=AuthSettings(
        issuer_url=f"{_PUBLIC_URL}/",
        resource_server_url=_PUBLIC_URL,
        client_registration_options=ClientRegistrationOptions(enabled=True),
    ),
)

# ------------------------------------------------------------------ #
# OAuth browser-callback route                                         #
# ------------------------------------------------------------------ #

_OAUTH_SUCCESS_HTML = (
    "<html><body style='font-family:sans-serif;text-align:center;margin-top:4rem'>"
    "<h2>qscreener: you're signed in</h2>"
    "<p>You can close this tab and return to your AI agent.</p></body></html>"
)
_OAUTH_FAILURE_HTML = (
    "<html><body style='font-family:sans-serif;text-align:center;margin-top:4rem'>"
    "<h2>qscreener: sign-in failed</h2>"
    "<p>The login link was invalid or expired. Try connecting again from your AI agent.</p></body></html>"
)


@mcp.custom_route("/oauth/callback", methods=["GET"])
async def _oauth_callback(request: Request) -> RedirectResponse | HTMLResponse:
    """Receive the CLI token from the web app and redirect the MCP client."""
    state = request.query_params.get("state")
    token = request.query_params.get("token")

    if not state or not token:
        return HTMLResponse(_OAUTH_FAILURE_HTML, status_code=400)

    redirect_url = store_auth_code(internal_state=state, cli_token=token)
    if redirect_url is None:
        return HTMLResponse(_OAUTH_FAILURE_HTML, status_code=400)

    return RedirectResponse(redirect_url, status_code=302)


# ------------------------------------------------------------------ #
# Bearer-token helpers                                                 #
# ------------------------------------------------------------------ #

_CLI_TOKEN_HEADER = "X-Stobot-CLI-Token"

_NOT_AUTHENTICATED = {
    "error": (
        "Not authenticated. In HTTP mode the MCP client handles login automatically "
        "via OAuth — reconnect to trigger the flow. In stdio mode, run "
        "'qscreener auth login' or set $QSCREENER_TOKEN."
    )
}


def _bearer_token() -> Optional[str]:
    """Resolve the CLI bearer token for the current call.

    Precedence: HTTP request header → ``$QSCREENER_TOKEN`` env var →
    ``~/.config/qscreener/credentials.json`` (stdio mode).
    """
    # 1. Active HTTP request (set by FastMCP auth middleware or sent manually)
    try:
        headers = mcp.get_context().request_context.request.headers
        if t := headers.get(_CLI_TOKEN_HEADER):
            return t.strip() or None
        if auth := headers.get("authorization", ""):
            if auth.lower().startswith("bearer "):
                return auth[len("bearer "):].strip() or None
    except Exception:  # noqa: BLE001 - no active request (stdio) or no context
        pass

    # 2. Env var override (convenient for CI / local dev)
    if t := os.environ.get("QSCREENER_TOKEN"):
        return t

    # 3. Credentials file written by `qscreener auth login`
    config_dir = Path(os.environ.get("QSCREENER_CONFIG_DIR", Path.home() / ".config" / "qscreener"))
    try:
        return json.loads((config_dir / "credentials.json").read_text()).get("token")
    except Exception:  # noqa: BLE001
        return None


def _guard(fn: Callable[[ApiClient], Any]) -> Any:
    """Run ``fn`` with an authenticated ApiClient; return an error dict on failure."""
    token = _bearer_token()
    if not token:
        return dict(_NOT_AUTHENTICATED)
    client = ApiClient(api_url=_API_URL, token=token)
    try:
        result = fn(client)
        return result if result is not None else {"status": "ok"}
    except ApiError as exc:
        return {"error": str(exc)}


# ------------------------------------------------------------------ #
# MCP tools                                                            #
# ------------------------------------------------------------------ #

@mcp.tool()
def auth_status() -> dict:
    """Report whether a CLI token is present and which user it authenticates as."""
    if not _bearer_token():
        return {"signed_in": False, "hint": "Connect via an MCP client to trigger OAuth login."}
    return _guard(lambda c: c.get("/v1/cli/auth/whoami"))


@mcp.tool()
def health() -> dict:
    """Check API and database health."""
    return _guard(lambda c: c.get("/health"))


@mcp.tool()
def account_profile() -> dict:
    """Return the signed-in user's profile (email, username, organization)."""
    return _guard(lambda c: c.get("/v1/auth/profile"))


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _filters(
    *,
    ticker: Optional[str] = None,
    sectors: Optional[list[str]] = None,
    industries: Optional[list[str]] = None,
    countries: Optional[list[str]] = None,
    currencies: Optional[list[str]] = None,
    exchanges: Optional[list[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
) -> dict[str, Any]:
    return _clean({
        "ticker": ticker,
        "sectors": sectors or None,
        "industries": industries or None,
        "countries": countries or None,
        "currencies": currencies or None,
        "exchanges": exchanges or None,
        "min_score": min_score,
        "max_score": max_score,
        "min_market_cap": min_market_cap,
        "max_market_cap": max_market_cap,
    })


@mcp.tool()
def scores_list(
    ticker: Optional[str] = None,
    sectors: Optional[list[str]] = None,
    industries: Optional[list[str]] = None,
    countries: Optional[list[str]] = None,
    currencies: Optional[list[str]] = None,
    exchanges: Optional[list[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    min_market_cap_usd: Optional[float] = None,
    max_market_cap_usd: Optional[float] = None,
    sort_by: str = "quality_score",
    sort_order: str = "desc",
    offset: int = 0,
    limit: int = 50,
    include_duplicates: bool = False,
) -> dict:
    """List scored tickers with optional filters. Market caps are in USD."""
    body = _filters(
        ticker=ticker, sectors=sectors, industries=industries, countries=countries,
        currencies=currencies, exchanges=exchanges, min_score=min_score, max_score=max_score,
        min_market_cap=min_market_cap_usd, max_market_cap=max_market_cap_usd,
    )
    params = {
        "offset": offset, "limit": limit,
        "include_duplicates": str(include_duplicates).lower(),
        "sort_by": sort_by, "sort_order": sort_order,
    }
    return _guard(lambda c: c.post("/v1/scores/list", params=params, json=body))


@mcp.tool()
def scores_top(limit: int = 20) -> dict:
    """Return the top tickers by quality score as a {ticker: score} map."""
    return _guard(lambda c: c.get("/v1/scores/", params={"limit": limit}))


@mcp.tool()
def scores_show(ticker: str) -> dict:
    """Return the score row(s) for a single ticker."""
    body = _filters(ticker=ticker.upper())
    return _guard(lambda c: c.post("/v1/scores/list", params={"limit": 5, "include_duplicates": "true"}, json=body))


@mcp.tool()
def scores_statistics(
    sectors: Optional[list[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    min_market_cap_usd: Optional[float] = None,
    max_market_cap_usd: Optional[float] = None,
) -> dict:
    """Return min/max/average score statistics for a filtered universe."""
    body = _filters(
        sectors=sectors, min_score=min_score, max_score=max_score,
        min_market_cap=min_market_cap_usd, max_market_cap=max_market_cap_usd,
    )
    return _guard(lambda c: c.post("/v1/scores/statistics", json=body))


@mcp.tool()
def scores_market_cap(sectors: Optional[list[str]] = None, min_score: Optional[float] = None) -> dict:
    """Return aggregated total market cap (USD) for a filtered universe."""
    body = _filters(sectors=sectors, min_score=min_score)
    return _guard(lambda c: c.post("/v1/scores/total-market-cap", json=body))


@mcp.tool()
def score_compute(
    config: dict,
    sectors: Optional[list[str]] = None,
    industries: Optional[list[str]] = None,
    countries: Optional[list[str]] = None,
    currencies: Optional[list[str]] = None,
    exchanges: Optional[list[str]] = None,
    min_market_cap_usd: Optional[float] = None,
    max_market_cap_usd: Optional[float] = None,
    sort_by: str = "quality_score",
    sort_order: str = "desc",
    offset: int = 0,
    limit: int = 50,
    include_duplicates: bool = False,
) -> dict:
    """Compute custom scores from a CustomScoreConfig object, restricted to a filtered universe.

    The list filters (``sectors``, ``industries``, ``countries``, ``currencies``,
    ``exchanges``) narrow the universe the custom score is computed over; each uses
    OR logic within itself and AND logic across filters. Market caps are in USD.
    """
    body = {
        "score_request": {"config": config},
        "filters": _filters(
            sectors=sectors,
            industries=industries,
            countries=countries,
            currencies=currencies,
            exchanges=exchanges,
            min_market_cap=min_market_cap_usd,
            max_market_cap=max_market_cap_usd,
        ),
    }
    params = {
        "offset": offset, "limit": limit,
        "include_duplicates": str(include_duplicates).lower(),
        "sort_by": sort_by, "sort_order": sort_order,
    }
    return _guard(lambda c: c.post("/v1/scores/custom", params=params, json=body))


@mcp.tool()
def screen_share(config: dict) -> dict:
    """Create a shareable link for a screen (CustomScoreConfig) and return its URL.

    Persists the screen configuration and returns a short, public link that can be
    copy-pasted to anyone — recipients open it to view and load the exact screen.
    The link is content-addressed: sharing an identical config returns the same URL
    instead of creating a duplicate.

    Args:
        config: The complete CustomScoreConfig to share (metric groups, weights,
            filters, and parameters), as produced by ``score_compute``/``systems_*``.

    Returns:
        dict with ``url`` (the shareable link to copy-paste), ``slug`` (the short
        identifier), ``created`` (True if newly created, False if an identical
        screen already existed), and ``view_count``.
    """
    def call(c: ApiClient) -> dict:
        resp = c.post("/v1/screens", json={"config": config})
        slug = resp.get("slug") if isinstance(resp, dict) else None
        if not slug:
            return resp
        return {
            "url": f"{_WEBSITE_URL}/s/{slug}",
            "slug": slug,
            "created": resp.get("created", False),
            "view_count": resp.get("view_count", 0),
        }
    return _guard(call)


@mcp.tool()
def filters_list() -> dict:
    """Return available filter values (sectors, industries, countries, currencies, exchanges)."""
    return _guard(lambda c: c.get("/v1/filters/values"))


@mcp.tool()
def tickers_list(limit: Optional[int] = None) -> dict:
    """Return available tickers, optionally truncated to ``limit``."""
    def call(c: ApiClient) -> dict:
        data = c.get("/v1/tickers/")
        tickers = data.get("tickers", []) if isinstance(data, dict) else []
        if limit is not None:
            tickers = tickers[:limit]
        return {"tickers": tickers, "count": len(tickers)}
    return _guard(call)


@mcp.tool()
def tickers_search(query: str) -> dict:
    """Search available tickers by case-insensitive substring."""
    def call(c: ApiClient) -> dict:
        data = c.get("/v1/tickers/")
        tickers = data.get("tickers", []) if isinstance(data, dict) else []
        needle = query.upper()
        matches = [t for t in tickers if needle in t.upper()]
        return {"tickers": matches, "count": len(matches)}
    return _guard(call)


@mcp.tool()
def history_ticker(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    scoring_system_id: Optional[int] = None,
) -> dict:
    """Return score history for a single ticker (dates: YYYY-MM-DD)."""
    params = _clean({"start_date": start, "end_date": end, "scoring_system_id": scoring_system_id})
    return _guard(lambda c: c.get(f"/v1/scores/history/{ticker.upper()}", params=params))


@mcp.tool()
def history_batch(
    tickers: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    scoring_system_id: Optional[int] = None,
) -> dict:
    """Return score history for several tickers at once."""
    body = _clean({
        "tickers": [t.upper() for t in tickers],
        "start_date": start,
        "end_date": end,
        "scoring_system_id": scoring_system_id,
    })
    return _guard(lambda c: c.post("/v1/scores/history/batch", json=body))


@mcp.tool()
def history_top(top: int = 10, scoring_system_id: Optional[int] = None) -> dict:
    """Fetch the top-N tickers and return their score history."""
    def call(c: ApiClient) -> dict:
        top_scores = c.get("/v1/scores/", params={"limit": top})
        symbols = list((top_scores or {}).keys())
        if not symbols:
            return {"results": []}
        body = _clean({"tickers": symbols, "scoring_system_id": scoring_system_id})
        return c.post("/v1/scores/history/batch", json=body)
    return _guard(call)


@mcp.tool()
def systems_list() -> dict:
    """List the user's saved scoring systems."""
    return _guard(lambda c: c.get("/v1/user/scores"))


@mcp.tool()
def systems_show(system_id: int) -> dict:
    """Show a saved scoring system by ID."""
    return _guard(lambda c: c.get(f"/v1/user/scores/{system_id}"))


@mcp.tool()
def systems_create(name: str, config: dict, description: Optional[str] = None) -> dict:
    """Create a saved scoring system from a config object."""
    return _guard(lambda c: c.post("/v1/user/scores", json=_clean({"name": name, "description": description, "config": config})))


@mcp.tool()
def systems_update(
    system_id: int,
    name: Optional[str] = None,
    config: Optional[dict] = None,
    description: Optional[str] = None,
) -> dict:
    """Update a saved scoring system."""
    return _guard(lambda c: c.put(f"/v1/user/scores/{system_id}", json=_clean({"name": name, "description": description, "config": config})))


@mcp.tool()
def systems_delete(system_id: int) -> dict:
    """Delete a saved scoring system."""
    return _guard(lambda c: c.delete(f"/v1/user/scores/{system_id}"))


@mcp.tool()
def systems_apply(system_id: int) -> dict:
    """Apply a saved scoring system (increments its usage count)."""
    return _guard(lambda c: c.post(f"/v1/user/scores/{system_id}/apply"))


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def main() -> None:
    """Console-script entry point.

    Transport is selected by ``QSCREENER_MCP_TRANSPORT`` (default ``stdio``).
    For HTTP transports the server binds to ``QSCREENER_MCP_HOST``
    (default ``0.0.0.0``) and ``$PORT`` / ``QSCREENER_MCP_PORT``
    (default ``8080``), serving MCP at ``/mcp`` and OAuth at standard paths.
    """
    transport = os.environ.get("QSCREENER_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return
    if transport not in {"streamable-http", "sse"}:
        raise SystemExit(
            f"Unsupported QSCREENER_MCP_TRANSPORT {transport!r}; "
            "use 'stdio', 'streamable-http', or 'sse'."
        )
    mcp.settings.port = int(os.environ.get("PORT") or os.environ.get("QSCREENER_MCP_PORT") or "8080")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
