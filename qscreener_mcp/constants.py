"""Shared constants for the qscreener MCP server.

Single home for the values that are fixed at build time: HTTP header names,
environment-variable names and their defaults, on-disk filenames, user-facing
messages, and the canonical tool names.

Two things previously lived in more than one module — the ``X-Stobot-CLI-Token``
header name and the ``QSCREENER_CONFIG_DIR`` fallback path — and had to be kept
in sync by hand. Collecting them here removes that risk.

Environment *values* are deliberately not resolved here: :mod:`qscreener_mcp.server`
still reads them at import time so the resolution order stays visible where it
matters. This module only supplies the names and the defaults.
"""

from enum import StrEnum

from qscreener_mcp import __version__

# ------------------------------------------------------------------ #
# HTTP headers sent to the backend API                                 #
# ------------------------------------------------------------------ #

# Opaque per-user bearer token. A dedicated header rather than
# ``Authorization: Bearer`` keeps it away from SuperTokens' session verification,
# which would otherwise try to parse it as an access token.
CLI_TOKEN_HEADER = "X-Stobot-CLI-Token"

# Identifies this client to the backend, which cannot otherwise tell MCP traffic
# apart from the qscreener CLI: both call the same endpoints with the same token
# header. ``CLIENT_OP_HEADER`` names the tool behind the call, so a request to a
# shared endpoint (scores_show and scores_list both POST /v1/scores/list) is
# still attributable to the tool the user actually invoked.
#
# Both are product-analytics metadata only — nothing about authentication or
# authorization depends on them.
CLIENT_HEADER = "X-Stobot-Client"
CLIENT_OP_HEADER = "X-Stobot-Client-Op"
CLIENT_ID = f"mcp/{__version__}"

# Per-request timeout for backend calls, in seconds.
DEFAULT_TIMEOUT = 60.0

# ------------------------------------------------------------------ #
# Environment variable names                                           #
# ------------------------------------------------------------------ #

ENV_API_URL = "QSCREENER_API_URL"
ENV_WEBSITE_URL = "QSCREENER_WEBSITE_URL"
ENV_MCP_PUBLIC_URL = "QSCREENER_MCP_PUBLIC_URL"
ENV_MCP_HOST = "QSCREENER_MCP_HOST"
ENV_MCP_PORT = "QSCREENER_MCP_PORT"
ENV_MCP_TRANSPORT = "QSCREENER_MCP_TRANSPORT"
ENV_TOKEN = "QSCREENER_TOKEN"
ENV_CONFIG_DIR = "QSCREENER_CONFIG_DIR"

# Set by the hosting platform (Railway), and takes precedence over ENV_MCP_PORT.
ENV_PLATFORM_PORT = "PORT"

# ------------------------------------------------------------------ #
# Defaults                                                             #
# ------------------------------------------------------------------ #

DEFAULT_API_URL = "http://localhost:8001"
DEFAULT_WEBSITE_URL = "http://localhost:3001"
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = "8080"
DEFAULT_TRANSPORT = "stdio"

# ------------------------------------------------------------------ #
# On-disk locations                                                    #
# ------------------------------------------------------------------ #

# Fallback config directory when ENV_CONFIG_DIR is unset; joined to the user's
# home directory by the caller.
DEFAULT_CONFIG_DIR_PARTS = (".config", "qscreener")

# Written by ``qscreener auth login``.
CREDENTIALS_FILENAME = "credentials.json"

# OAuth client registrations — these identify applications, not people.
MCP_CLIENTS_FILENAME = "mcp_clients.json"

# ------------------------------------------------------------------ #
# OAuth                                                                #
# ------------------------------------------------------------------ #

# Seconds. Codes are exchanged immediately; ten minutes is generous.
AUTH_CODE_TTL = 600

# ------------------------------------------------------------------ #
# User-facing messages                                                 #
# ------------------------------------------------------------------ #

NOT_AUTHENTICATED = {
    "error": (
        "Not authenticated. In HTTP mode the MCP client handles login automatically "
        "via OAuth — reconnect to trigger the flow. In stdio mode, run "
        "'qscreener auth login' or set $QSCREENER_TOKEN."
    )
}

OAUTH_SUCCESS_HTML = (
    "<html><body style='font-family:sans-serif;text-align:center;margin-top:4rem'>"
    "<h2>qscreener: you're signed in</h2>"
    "<p>You can close this tab and return to your AI agent.</p></body></html>"
)
OAUTH_FAILURE_HTML = (
    "<html><body style='font-family:sans-serif;text-align:center;margin-top:4rem'>"
    "<h2>qscreener: sign-in failed</h2>"
    "<p>The login link was invalid or expired. Try connecting again from your AI agent.</p></body></html>"
)

# ------------------------------------------------------------------ #
# Score-config normalization                                           #
# ------------------------------------------------------------------ #

# Filter keys that belong inside a config's nested ``filters`` block. Used to fold
# filters accidentally placed at the top level into ``filters`` during normalization.
CONFIG_FILTER_KEYS = (
    "sectors", "industries", "regions", "countries", "currencies", "exchanges",
    "min_market_cap", "max_market_cap", "min_score", "max_score", "ticker", "tickers",
)

# The tools expose market caps in USD (``min_market_cap_usd``), but a config's ``filters``
# block stores them in BILLIONS — the unit the web score builder reads and the backend
# persists. So these variants must be rescaled onto the canonical key, not merely renamed:
# the backend ignores unrecognized filter keys, silently widening the screen back to the
# full universe.
USD_MARKET_CAP_KEYS = {
    "min_market_cap_usd": "min_market_cap",
    "max_market_cap_usd": "max_market_cap",
}
USD_PER_BILLION = 1_000_000_000

# ------------------------------------------------------------------ #
# Response shaping                                                     #
# ------------------------------------------------------------------ #

# Score-list descriptions are truncated to this many characters before being
# handed to an LLM, to keep payloads small.
DESCRIPTION_LIMIT = 200

# ------------------------------------------------------------------ #
# Tools                                                                #
# ------------------------------------------------------------------ #


class Tool(StrEnum):
    """Canonical name of every tool exposed by this MCP server.

    Each member's value must match the name of the decorated tool function in
    :mod:`qscreener_mcp.server`, which is the name MCP clients call. The values
    also travel to the backend in :data:`CLIENT_OP_HEADER` and become the ``tool``
    property on usage-analytics events, so a typo would silently split or
    mislabel a tool's usage rather than raise.

    ``StrEnum`` (Python 3.11+) means members *are* strings: they serialize into
    headers and compare against plain strings without any conversion.
    """

    # Account and service status
    AUTH_STATUS = "auth_status"
    HEALTH = "health"
    ACCOUNT_PROFILE = "account_profile"

    # Scores
    SCORES_LIST = "scores_list"
    SCORES_TOP = "scores_top"
    SCORES_SHOW = "scores_show"
    SCORES_FOR_TICKERS = "scores_for_tickers"
    SCORES_STATISTICS = "scores_statistics"
    SCORES_MARKET_CAP = "scores_market_cap"
    SCORE_COMPUTE = "score_compute"

    # Sharing, filters and tickers
    SCREEN_SHARE = "screen_share"
    FILTERS_LIST = "filters_list"
    TICKERS_LIST = "tickers_list"
    TICKERS_SEARCH = "tickers_search"

    # Score history
    HISTORY_TICKER = "history_ticker"
    HISTORY_BATCH = "history_batch"
    HISTORY_TOP = "history_top"

    # Saved scoring systems
    SYSTEMS_LIST = "systems_list"
    SYSTEMS_SHOW = "systems_show"
    SYSTEMS_CREATE = "systems_create"
    SYSTEMS_UPDATE = "systems_update"
    SYSTEMS_DELETE = "systems_delete"
    SYSTEMS_APPLY = "systems_apply"
