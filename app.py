"""Vercel Python entrypoint.

Exports a FastAPI ``app`` so Vercel’s Python / FastAPI preset loads this as a
single Function. The FastMCP streamable-HTTP Starlette app is mounted at ``/``,
which already serves ``/mcp``, ``/.well-known/*``, ``/authorize``, ``/token``,
``/register``, and ``/oauth/callback``. Docker and Railway keep using
``qscreener-mcp`` / ``mcp.run()`` and never import this file.

GET /mcp is answered with 405 Method Not Allowed. This server uses stateless
JSON responses and does not offer a Streamable HTTP SSE stream; a GET would
otherwise hold the serverless function until ``maxDuration``.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from qscreener_mcp.server import mcp


def _is_mcp_endpoint(path: str) -> bool:
    return path.rstrip("/") == "/mcp"


class RejectMcpGetMiddleware(BaseHTTPMiddleware):
    """Reject Streamable HTTP GET/HEAD on /mcp so Vercel does not hold SSE."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD"} and _is_mcp_endpoint(request.url.path):
            body = b"" if request.method == "HEAD" else b"Method Not Allowed"
            return Response(
                content=body,
                status_code=405,
                headers={"Allow": "POST"},
                media_type="text/plain; charset=utf-8",
            )
        return await call_next(request)


@asynccontextmanager
async def _noop_lifespan(_app: Starlette):
    """Mounted-app lifespan must not call ``session_manager.run()`` a second time."""
    yield


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # streamable_http_app() lazily creates the session manager. The inner
    # Starlette lifespan is replaced with a no-op so only this context starts it.
    async with mcp.session_manager.run():
        yield


def create_app() -> FastAPI:
    """Build the FastAPI host that Vercel (and tests) import as ``app``."""
    inner = mcp.streamable_http_app()
    inner.router.lifespan_context = _noop_lifespan

    application = FastAPI(title="qscreener-mcp", lifespan=_lifespan)
    application.add_middleware(RejectMcpGetMiddleware)
    application.mount("/", inner)
    return application


app = create_app()
