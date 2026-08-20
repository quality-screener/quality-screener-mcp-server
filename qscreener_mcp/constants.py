"""Shared constants for the qscreener MCP server.

The :class:`Tool` members are the canonical names of the MCP tools. They travel
to the backend in the ``X-Stobot-Client-Op`` header, where they become the
``tool`` property on usage-analytics events — so a typo here would silently
split or mislabel a tool's usage rather than raise. Referring to the enum
instead of a bare string keeps every call site checkable.

``StrEnum`` (Python 3.11+) means members *are* strings: they serialize into
headers and compare against plain strings without any conversion.
"""

from enum import StrEnum


class Tool(StrEnum):
    """Canonical name of every tool exposed by this MCP server.

    Each member's value must match the name of the decorated tool function in
    :mod:`qscreener_mcp.server`, which is the name MCP clients call.
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
