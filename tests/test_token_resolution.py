"""Tests for CLI bearer-token resolution in the MCP server.

``server._bearer_token`` resolves the token with the precedence:
HTTP request header → ``$QSCREENER_TOKEN`` env var →
``$QSCREENER_CONFIG_DIR/credentials.json`` (stdio mode).
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

from qscreener_mcp import server


def _fake_context(headers: Optional[dict[str, str]]) -> SimpleNamespace:
    """Build a fake FastMCP context exposing ``request_context.request.headers``.

    Args:
        headers: Header mapping for the simulated HTTP request, or ``None`` to
            simulate a stdio call with no underlying HTTP request.

    Returns:
        An object shaped like the context returned by ``mcp.get_context()``.
    """
    request = None if headers is None else SimpleNamespace(headers=headers)
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest.fixture
def no_local_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Ensure no env-var or credentials-file token leaks into a test.

    Args:
        monkeypatch: pytest fixture for editing the environment.
        tmp_path: An empty temporary directory used as the config dir.

    Returns:
        The empty config directory (no ``credentials.json`` present).
    """
    monkeypatch.delenv("QSCREENER_TOKEN", raising=False)
    monkeypatch.setenv("QSCREENER_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_bearer_token_reads_cli_token_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """The custom ``X-Stobot-CLI-Token`` header is returned verbatim (trimmed)."""
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context({"X-Stobot-CLI-Token": "  tok-abc  "}))
    assert server._bearer_token() == "tok-abc"


def test_bearer_token_reads_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``Authorization: Bearer <token>`` header is accepted as a fallback."""
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context({"authorization": "Bearer tok-xyz"}))
    assert server._bearer_token() == "tok-xyz"


def test_bearer_token_prefers_cli_header_over_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both headers are present the dedicated CLI header wins."""
    headers = {"X-Stobot-CLI-Token": "cli", "authorization": "Bearer bearer"}
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context(headers))
    assert server._bearer_token() == "cli"


def test_bearer_token_header_preferred_over_env(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """The per-request header takes precedence over the ``$QSCREENER_TOKEN`` env var."""
    monkeypatch.setenv("QSCREENER_TOKEN", "from-env")
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context({"X-Stobot-CLI-Token": "from-header"}))
    assert server._bearer_token() == "from-header"


def test_bearer_token_falls_back_to_env(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """Without a request header, ``$QSCREENER_TOKEN`` is used (stdio mode)."""
    monkeypatch.setenv("QSCREENER_TOKEN", "from-env")
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context(None))
    assert server._bearer_token() == "from-env"


def test_bearer_token_falls_back_to_credentials_file(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """Without a header or env var, the credentials file token is used."""
    (no_local_token / "credentials.json").write_text(json.dumps({"token": "from-file"}))
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context(None))
    assert server._bearer_token() == "from-file"


def test_bearer_token_none_without_any_source(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """Over stdio with no env var or credentials file, no token can be resolved."""
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context(None))
    assert server._bearer_token() is None


def test_bearer_token_none_when_context_unavailable(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """A missing/raising context resolves to ``None`` rather than erroring."""
    def _raise() -> None:
        raise LookupError("no active request")

    monkeypatch.setattr(server.mcp, "get_context", _raise)
    assert server._bearer_token() is None


def test_guard_returns_error_without_token(monkeypatch: pytest.MonkeyPatch, no_local_token: Path) -> None:
    """``_guard`` short-circuits with an auth error when no token is available."""
    monkeypatch.setattr(server.mcp, "get_context", lambda: _fake_context(None))
    result = server._guard(lambda client: {"unreachable": True})
    assert "error" in result
    assert "Not authenticated" in result["error"]
