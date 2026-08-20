"""Tests for the client-identification headers sent to the backend API.

The backend cannot otherwise tell MCP traffic apart from the qscreener CLI: both
call the same endpoints with the same ``X-Stobot-CLI-Token`` header. These
headers are what make MCP usage attributable in product analytics.
"""

from qscreener_mcp import __version__
from qscreener_mcp.client import (
    CLI_TOKEN_HEADER,
    CLIENT_HEADER,
    CLIENT_ID,
    CLIENT_OP_HEADER,
    ApiClient,
)


def test_headers_identify_the_mcp_client() -> None:
    """Every request announces the client name and version."""
    headers = ApiClient(api_url="http://api.test", token="tok")._headers()

    assert headers[CLIENT_HEADER] == CLIENT_ID
    assert headers[CLIENT_HEADER].startswith("mcp/")
    assert headers[CLI_TOKEN_HEADER] == "tok"
    assert headers["Accept"] == "application/json"


def test_client_id_carries_the_package_version() -> None:
    """The client header is ``mcp/<version>`` so releases are distinguishable."""
    assert CLIENT_ID == f"mcp/{__version__}"


def test_tool_name_is_sent_when_known() -> None:
    """The tool name lets shared endpoints be attributed to the right tool.

    ``scores_show`` and ``scores_list`` both POST ``/v1/scores/list``, so the
    endpoint alone cannot identify which tool the user invoked.
    """
    headers = ApiClient(api_url="http://api.test", token="tok", tool="scores_show")._headers()
    assert headers[CLIENT_OP_HEADER] == "scores_show"


def test_tool_header_is_omitted_when_unset() -> None:
    """No tool name means no header, rather than an empty value."""
    headers = ApiClient(api_url="http://api.test", token="tok")._headers()
    assert CLIENT_OP_HEADER not in headers


def test_trailing_slash_is_stripped_from_api_url() -> None:
    """Base URL normalization is unaffected by the added headers."""
    assert ApiClient(api_url="http://api.test/", token="tok")._api_url == "http://api.test"
