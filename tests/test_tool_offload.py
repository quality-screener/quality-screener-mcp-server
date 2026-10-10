"""Tests that tools run off the event loop, and that auth failures map to the right HTTP status.

Before this change every tool was a plain ``def`` that FastMCP ran directly on the event
loop, so one slow backend call froze the whole server, concurrent bearer-token checks
timed out, and those requests were answered with 401, which makes MCP clients discard
their credentials.
"""

import contextvars
import threading
import time
from typing import Optional

import anyio
import pytest
from starlette.testclient import TestClient

from qscreener_mcp import oauth, server
from qscreener_mcp.oauth import _Verdict

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def temp_tool():
    """Register throwaway tools through ``server._tool`` and remove them afterwards."""
    names: list[str] = []

    def register(fn):
        server._tool(name=fn.__name__)(fn)
        names.append(fn.__name__)
        return fn

    yield register
    for name in names:
        server.mcp._tool_manager._tools.pop(name, None)


def test_every_tool_is_registered_async() -> None:
    tools = server.mcp._tool_manager.list_tools()
    assert len(tools) == 23
    assert all(t.is_async for t in tools)


def test_decorator_returns_original_sync_function() -> None:
    # Module-level callers and the existing tests call tools directly and synchronously.
    assert not hasattr(server.health, "__await__")
    assert server.mcp._tool_manager.get_tool("health").fn.__wrapped__ is server.health


async def test_slow_tool_does_not_block_event_loop(temp_tool) -> None:
    @temp_tool
    def _test_slow_tool() -> dict:
        time.sleep(0.5)  # stands in for a slow blocking backend call
        return {"thread": threading.current_thread().name}

    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await anyio.sleep(0.02)
            ticks += 1

    async with anyio.create_task_group() as tg:
        tg.start_soon(heartbeat)
        await server.mcp.call_tool("_test_slow_tool", {})
        ticks_while_tool_ran = ticks
        tg.cancel_scope.cancel()

    # On the event loop the heartbeat would be frozen for the whole 0.5 s (0-1 ticks);
    # in a worker thread it keeps ticking roughly every 20 ms.
    assert ticks_while_tool_ran >= 10


async def test_context_propagates_to_worker_thread(temp_tool) -> None:
    marker: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("marker", default=None)
    seen: dict = {}

    @temp_tool
    def _test_context_tool() -> dict:
        seen["value"] = marker.get()
        seen["thread"] = threading.current_thread() is not threading.main_thread()
        return {}

    marker.set("request-123")
    await server.mcp.call_tool("_test_context_tool", {})
    assert seen == {"value": "request-123", "thread": True}


# ------------------------------------------------------------------ #
# HTTP layer: invalid token -> 401, backend outage -> 5xx (not 401)    #
# ------------------------------------------------------------------ #


def _post_mcp(monkeypatch: pytest.MonkeyPatch, verdict: _Verdict) -> int:
    monkeypatch.setattr(oauth, "_validated", {})
    monkeypatch.setattr(oauth, "TOKEN_VALIDATION_RETRY_DELAY", 0)

    async def fake(token: str) -> tuple[_Verdict, Optional[str]]:
        return verdict, ("user-1" if verdict is _Verdict.VALID else None)

    monkeypatch.setattr(server._oauth, "_validate_with_backend", fake)
    client = TestClient(server.mcp.streamable_http_app(), raise_server_exceptions=False)
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer some-token", "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )
    return response.status_code


def test_http_rejected_token_is_401(monkeypatch) -> None:
    assert _post_mcp(monkeypatch, _Verdict.INVALID) == 401


def test_http_backend_outage_is_not_401(monkeypatch) -> None:
    status = _post_mcp(monkeypatch, _Verdict.UNAVAILABLE)
    assert status >= 500
