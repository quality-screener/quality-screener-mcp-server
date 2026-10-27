"""Tests for in-memory and signed (serverless-safe) OAuth state.

Access tokens are the backend CLI token and are validated by whoami — they
need no local store. Pending state, authorization codes, and registered
clients do, and those three must survive a cold start when a signing key is
set (Vercel) while remaining unchanged when it is not (Railway / local).
"""

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from mcp.server.auth.provider import AuthorizationParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from qscreener_mcp import oauth
from qscreener_mcp.constants import SIGNED_TYP_CLIENT, SIGNED_TYP_CODE, SIGNED_TYP_PENDING
from qscreener_mcp.oauth import StobotOAuthProvider, store_auth_code


SIGNING_KEY = "test-signing-key-not-a-secret-32b+"


def _client(client_id: str = "client-1") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret="s3cret",
        redirect_uris=[AnyUrl("https://client.example/cb")],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )


def _params() -> AuthorizationParams:
    return AuthorizationParams(
        state="oauth-state",
        scopes=["mcp"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("https://client.example/cb"),
        redirect_uri_provided_explicitly=True,
    )


def _provider(*, signing_key: str | None) -> StobotOAuthProvider:
    return StobotOAuthProvider(
        api_url="https://api.example",
        website_url="https://app.example",
        mcp_public_url="https://mcp.example",
        signing_key=signing_key if signing_key is not None else "",
    )


@pytest.fixture
def isolated_oauth(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Give each test a clean in-memory store and config dir."""
    monkeypatch.setenv("QSCREENER_CONFIG_DIR", str(tmp_path))
    oauth._clients.clear()
    oauth._pending.clear()
    oauth._codes.clear()
    oauth._signing_key = None
    yield
    oauth._clients.clear()
    oauth._pending.clear()
    oauth._codes.clear()
    oauth._signing_key = None


def test_memory_authorize_roundtrip_without_signing_key(isolated_oauth: None) -> None:
    """Unsigned mode keeps the original in-memory pending → code → token flow."""

    async def _run() -> None:
        provider = _provider(signing_key="")
        client = _client()
        await provider.register_client(client)
        assert client.client_id == "client-1"

        authorize_url = await provider.authorize(client, _params())
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        assert state in oauth._pending
        # A random state token is not a JWT.
        with pytest.raises(jwt.DecodeError):
            jwt.decode(state, options={"verify_signature": False})

        redirect = store_auth_code(state, "cli-token-1")
        assert redirect is not None
        code = parse_qs(urlparse(redirect).query)["code"][0]
        loaded = await provider.load_authorization_code(client, code)
        assert loaded is not None
        token = await provider.exchange_authorization_code(client, loaded)
        assert token.access_token == "cli-token-1"

        # Same-process codes are one-time.
        oauth._codes.clear()
        assert await provider.load_authorization_code(client, code) is None

    asyncio.run(_run())


def test_signed_flow_survives_empty_memory(isolated_oauth: None) -> None:
    """A second process with the same key can finish a login started elsewhere."""

    async def _run() -> None:
        provider = _provider(signing_key=SIGNING_KEY)
        client = _client("will-be-replaced")
        await provider.register_client(client)
        signed_id = client.client_id
        assert signed_id
        claims = jwt.decode(signed_id, SIGNING_KEY, algorithms=["HS256"])
        assert claims["typ"] == SIGNED_TYP_CLIENT

        authorize_url = await provider.authorize(client, _params())
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        assert jwt.decode(state, SIGNING_KEY, algorithms=["HS256"])["typ"] == SIGNED_TYP_PENDING

        # Simulate a different Vercel invocation: drop every in-memory record.
        oauth._clients.clear()
        oauth._pending.clear()
        oauth._codes.clear()

        recovered = await provider.get_client(signed_id)
        assert recovered is not None
        assert recovered.client_secret == "s3cret"

        redirect = store_auth_code(state, "cli-token-2")
        assert redirect is not None
        code = parse_qs(urlparse(redirect).query)["code"][0]
        assert jwt.decode(code, SIGNING_KEY, algorithms=["HS256"])["typ"] == SIGNED_TYP_CODE

        oauth._codes.clear()
        loaded = await provider.load_authorization_code(recovered, code)
        assert loaded is not None
        token = await provider.exchange_authorization_code(recovered, loaded)
        assert token.access_token == "cli-token-2"

    asyncio.run(_run())


def test_signed_state_rejected_with_wrong_key(isolated_oauth: None) -> None:
    """A JWT minted with a different key is treated as an unknown login."""

    async def _run() -> None:
        _provider(signing_key=SIGNING_KEY)
        other = _sign_pending(key="some-other-key-that-is-32-bytes!")
        assert store_auth_code(other, "cli-token") is None

    asyncio.run(_run())


def test_unsigned_callback_unknown_state_is_none(isolated_oauth: None) -> None:
    """Without a signing key, a state that is not in memory cannot be recovered."""
    _provider(signing_key="")
    assert store_auth_code("no-such-state", "cli-token") is None


def test_exchange_unknown_code_raises(isolated_oauth: None) -> None:
    async def _run() -> None:
        provider = _provider(signing_key="")
        client = _client()
        from mcp.server.auth.provider import AuthorizationCode

        with pytest.raises(TokenError):
            await provider.exchange_authorization_code(
                client,
                AuthorizationCode(
                    code="missing",
                    scopes=[],
                    expires_at=0,
                    client_id=client.client_id or "client-1",
                    code_challenge="x",
                    redirect_uri=AnyUrl("https://client.example/cb"),
                    redirect_uri_provided_explicitly=True,
                ),
            )

    asyncio.run(_run())


def _sign_pending(*, key: str) -> str:
    return oauth._sign(
        {
            "client_id": "client-1",
            "redirect_uri": "https://client.example/cb",
            "oauth_state": "s",
            "code_challenge": "c",
            "scopes": [],
        },
        key,
        600,
        SIGNED_TYP_PENDING,
    )
