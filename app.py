"""Vercel Python entrypoint.

Exports a FastAPI ``app`` so Vercel’s Python / FastAPI preset loads this as a
single Function. The FastMCP streamable-HTTP Starlette app is mounted at ``/``,
which already serves ``/mcp``, ``/.well-known/*``, ``/authorize``, ``/token``,
``/register``, and ``/oauth/callback``. Docker and Railway keep using
``qscreener-mcp`` / ``mcp.run()`` and never import this file.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.applications import Starlette

from qscreener_mcp.server import mcp


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
    application.mount("/", inner)
    return application


app = create_app()
