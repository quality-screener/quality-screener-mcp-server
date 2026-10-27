"""Tests for the ASGI / Vercel entrypoint and public-URL resolution."""

from pathlib import Path

import pytest
from starlette.routing import Mount, Route

from qscreener_mcp import server


def _route_paths(app: object) -> list[str]:
    """Collect path strings from a Starlette (or mounted FastAPI) app."""
    paths: list[str] = []
    routes = getattr(app, "routes", []) or []
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            paths.append(path)
        if isinstance(route, Mount) and hasattr(route, "app"):
            paths.extend(_route_paths(route.app))
        elif isinstance(route, Route):
            continue
    return paths


def test_http_transport_is_stateless() -> None:
    """Serverless hosts cannot keep Streamable HTTP sessions in process memory."""
    assert server.mcp.settings.stateless_http is True
    assert server.mcp.settings.json_response is True


def test_http_app_exposes_mcp_oauth_and_callback_routes() -> None:
    """The ASGI app must serve /mcp, well-known metadata, and /oauth/callback."""
    app = server.http_app()
    paths = _route_paths(app)
    assert "/mcp" in paths
    assert "/oauth/callback" in paths
    assert any(p.endswith("/oauth-authorization-server") or "/.well-known/" in p for p in paths)
    assert "/authorize" in paths
    assert "/token" in paths
    assert "/register" in paths


def test_vercel_app_mounts_the_mcp_routes() -> None:
    """Vercel loads FastAPI ``app`` from app.py; the MCP routes sit underneath."""
    import app as vercel_app

    assert vercel_app.app is not None
    paths = _route_paths(vercel_app.app)
    assert "/mcp" in paths
    assert "/oauth/callback" in paths
    assert "/authorize" in paths


def test_public_url_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QSCREENER_MCP_PUBLIC_URL", "https://mcp.example.com/")
    monkeypatch.setenv("VERCEL_URL", "preview.vercel.app")
    assert server._public_url() == "https://mcp.example.com"


def test_public_url_falls_back_to_vercel_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QSCREENER_MCP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("VERCEL_URL", "my-app-abc.vercel.app")
    assert server._public_url() == "https://my-app-abc.vercel.app"


def test_public_url_accepts_vercel_url_with_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QSCREENER_MCP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("VERCEL_URL", "https://already-schemed.vercel.app")
    assert server._public_url() == "https://already-schemed.vercel.app"


def test_public_url_localhost_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QSCREENER_MCP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("QSCREENER_MCP_PORT", raising=False)
    assert server._public_url() == "http://localhost:8080"


def test_app_py_exists_at_repo_root() -> None:
    """Vercel’s Python preset looks for app.py next to pyproject.toml."""
    assert (Path(__file__).resolve().parents[1] / "app.py").is_file()
