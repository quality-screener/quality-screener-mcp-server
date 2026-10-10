"""Tests for token validation and refresh in ``qscreener_mcp.oauth``.

The failure these guard against: any hiccup in the backend ``whoami`` call used to be
answered with a 401, and with no refresh token the MCP client had to send the user back
through a browser login. Clients discard credentials on a 401, so a slow backend signed
users out. Now only a definitive 401/403 from the backend rejects a token.
"""

import time
from typing import Optional

import httpx
import pytest
from mcp.server.auth.provider import TokenError
from mcp.shared.auth import OAuthClientInformationFull

from qscreener_mcp import constants, oauth
from qscreener_mcp.oauth import BackendUnavailableError, StobotOAuthProvider, _Verdict

TOKEN = "cli-token-abc"

# Async tests run on anyio's bundled pytest plugin (no extra test dependency).
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the module-level validation cache and skip retry sleeps."""
    monkeypatch.setattr(oauth, "_validated", {})
    monkeypatch.setattr(oauth, "TOKEN_VALIDATION_RETRY_DELAY", 0)


@pytest.fixture
def provider() -> StobotOAuthProvider:
    return StobotOAuthProvider(api_url="http://backend", website_url="http://web", mcp_public_url="http://mcp")


@pytest.fixture
def client_info() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(client_id="client-1", redirect_uris=["http://127.0.0.1:9/cb"])


def _script(monkeypatch: pytest.MonkeyPatch, provider: StobotOAuthProvider, *verdicts: _Verdict) -> list[str]:
    """Make the backend return ``verdicts`` in order (last one repeats); return a call log."""
    calls: list[str] = []
    seq = list(verdicts)

    async def fake(token: str) -> tuple[_Verdict, Optional[str]]:
        calls.append(token)
        v = seq.pop(0) if len(seq) > 1 else seq[0]
        return v, ("user-1" if v is _Verdict.VALID else None)

    monkeypatch.setattr(provider, "_validate_with_backend", fake)
    return calls


def _age_cache(token: str, seconds: float) -> None:
    """Pretend the token was last confirmed ``seconds`` ago."""
    key = oauth._token_key(token)
    user_id, _ = oauth._validated[key]
    oauth._validated[key] = (user_id, time.monotonic() - seconds)


# ------------------------------------------------------------------ #
# load_access_token                                                    #
# ------------------------------------------------------------------ #


async def test_valid_token_is_cached(monkeypatch, provider) -> None:
    calls = _script(monkeypatch, provider, _Verdict.VALID)
    first = await provider.load_access_token(TOKEN)
    second = await provider.load_access_token(TOKEN)
    assert first is not None and first.subject == "user-1"
    assert second is not None
    assert len(calls) == 1  # second call served from the positive cache


async def test_rejected_token_returns_none_and_evicts(monkeypatch, provider) -> None:
    _script(monkeypatch, provider, _Verdict.VALID)
    await provider.load_access_token(TOKEN)
    _age_cache(TOKEN, constants.TOKEN_CACHE_TTL + 1)
    _script(monkeypatch, provider, _Verdict.INVALID)
    assert await provider.load_access_token(TOKEN) is None
    assert oauth._token_key(TOKEN) not in oauth._validated


async def test_unavailable_backend_without_history_raises_not_401(monkeypatch, provider) -> None:
    calls = _script(monkeypatch, provider, _Verdict.UNAVAILABLE)
    with pytest.raises(BackendUnavailableError):
        await provider.load_access_token(TOKEN)
    assert len(calls) == 1 + constants.TOKEN_VALIDATION_RETRIES


async def test_transient_failure_then_success_is_retried(monkeypatch, provider) -> None:
    calls = _script(monkeypatch, provider, _Verdict.UNAVAILABLE, _Verdict.VALID)
    assert await provider.load_access_token(TOKEN) is not None
    assert len(calls) == 2


async def test_unavailable_backend_accepts_recently_confirmed_token(monkeypatch, provider) -> None:
    _script(monkeypatch, provider, _Verdict.VALID)
    await provider.load_access_token(TOKEN)
    _age_cache(TOKEN, constants.TOKEN_CACHE_TTL + 60)  # past the cache, inside the grace window
    _script(monkeypatch, provider, _Verdict.UNAVAILABLE)
    token = await provider.load_access_token(TOKEN)
    assert token is not None and token.subject == "user-1"


async def test_unavailable_backend_rejects_after_grace(monkeypatch, provider) -> None:
    _script(monkeypatch, provider, _Verdict.VALID)
    await provider.load_access_token(TOKEN)
    _age_cache(TOKEN, constants.TOKEN_GRACE_TTL + 1)
    _script(monkeypatch, provider, _Verdict.UNAVAILABLE)
    with pytest.raises(BackendUnavailableError):
        await provider.load_access_token(TOKEN)


async def test_refresh_token_is_not_a_bearer_credential(monkeypatch, provider) -> None:
    calls = _script(monkeypatch, provider, _Verdict.VALID)
    assert await provider.load_access_token(f"{constants.REFRESH_TOKEN_PREFIX}{TOKEN}") is None
    assert calls == []


# ------------------------------------------------------------------ #
# Backend response classification                                      #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, _Verdict.VALID),
        (401, _Verdict.INVALID),
        (403, _Verdict.INVALID),
        (404, _Verdict.UNAVAILABLE),
        (429, _Verdict.UNAVAILABLE),
        (500, _Verdict.UNAVAILABLE),
        (503, _Verdict.UNAVAILABLE),
    ],
)
async def test_whoami_status_classification(monkeypatch, provider, status, expected) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers[constants.CLI_TOKEN_HEADER] == TOKEN
        return httpx.Response(status, json={"user_id": "user-1"})

    real = httpx.AsyncClient
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    verdict, user_id = await provider._validate_with_backend(TOKEN)
    assert verdict is expected
    assert user_id == ("user-1" if expected is _Verdict.VALID else None)


async def test_whoami_timeout_is_unavailable(monkeypatch, provider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    verdict, _ = await provider._validate_with_backend(TOKEN)
    assert verdict is _Verdict.UNAVAILABLE


# ------------------------------------------------------------------ #
# Token issuance and refresh                                           #
# ------------------------------------------------------------------ #


async def test_code_exchange_issues_refresh_token(provider, client_info) -> None:
    oauth._pending["state-1"] = {
        "client_id": client_info.client_id,
        "redirect_uri": "http://127.0.0.1:9/cb",
        "oauth_state": "s",
        "code_challenge": "c",
        "scopes": [],
    }
    redirect = oauth.store_auth_code("state-1", TOKEN)
    code = httpx.URL(redirect).params["code"]
    auth_code = await provider.load_authorization_code(client_info, code)
    token = await provider.exchange_authorization_code(client_info, auth_code)
    assert token.access_token == TOKEN
    assert token.expires_in == constants.ACCESS_TOKEN_EXPIRES_IN
    assert token.refresh_token == f"{constants.REFRESH_TOKEN_PREFIX}{TOKEN}"


async def test_refresh_returns_same_cli_token_while_valid(monkeypatch, provider, client_info) -> None:
    _script(monkeypatch, provider, _Verdict.VALID)
    rt = await provider.load_refresh_token(client_info, f"{constants.REFRESH_TOKEN_PREFIX}{TOKEN}")
    assert rt is not None and rt.client_id == client_info.client_id
    token = await provider.exchange_refresh_token(client_info, rt, [])
    assert token.access_token == TOKEN
    assert token.refresh_token == rt.token


async def test_refresh_of_revoked_token_is_invalid_grant(monkeypatch, provider, client_info) -> None:
    _script(monkeypatch, provider, _Verdict.INVALID)
    rt = await provider.load_refresh_token(client_info, f"{constants.REFRESH_TOKEN_PREFIX}{TOKEN}")
    with pytest.raises(TokenError) as exc:
        await provider.exchange_refresh_token(client_info, rt, [])
    assert exc.value.error == "invalid_grant"


async def test_refresh_during_outage_is_server_error_not_invalid_grant(monkeypatch, provider, client_info) -> None:
    _script(monkeypatch, provider, _Verdict.UNAVAILABLE)
    rt = await provider.load_refresh_token(client_info, f"{constants.REFRESH_TOKEN_PREFIX}{TOKEN}")
    with pytest.raises(BackendUnavailableError):
        await provider.exchange_refresh_token(client_info, rt, [])


async def test_unknown_refresh_token_is_not_loaded(provider, client_info) -> None:
    assert await provider.load_refresh_token(client_info, "something-else") is None
