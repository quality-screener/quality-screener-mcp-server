"""MCP OAuth 2.0 authorization server provider for qscreener.

Bridges FastMCP's OAuth layer to the existing SuperTokens / CLI token stack
without requiring an external OAuth service.  The flow:

1. ``authorize()`` redirects the browser to the web app's ``/cli-auth`` page,
   the same bridge used by the CLI, with the MCP server's ``/oauth/callback``
   as the ``callback_url``.
2. The web app exchanges the SuperTokens session for a CLI token and redirects
   to ``/oauth/callback?token=<cli_token>&state=<internal_state>``.
3. ``store_auth_code()`` (called by the route handler) converts the CLI token
   into a short-lived authorization code and redirects the MCP client to its
   registered ``redirect_uri``.
4. ``exchange_authorization_code()`` returns the CLI token as the OAuth access
   token — no separate credential is minted; the CLI token IS the bearer.
5. ``load_access_token()`` validates incoming bearer tokens against the backend
   ``GET /v1/cli/auth/whoami`` endpoint, with a short positive cache.
6. A refresh token (``REFRESH_TOKEN_PREFIX`` + the CLI token) is issued alongside the
   access token, so a client whose access token is rejected can recover through the
   refresh grant instead of sending the user back through the browser.

Only a definitive backend answer (401/403) makes a token invalid. A backend that is
slow, down or rate-limiting is treated as *unavailable*: recently confirmed tokens
stay accepted for ``TOKEN_GRACE_TTL``, and otherwise the request fails with a server
error rather than a 401, because MCP clients discard their credentials on a 401.

All state is in-memory; suitable for single-process local and Railway deployments.
"""

import asyncio
import enum
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

_log = logging.getLogger(__name__)
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from qscreener_mcp.constants import (
    ACCESS_TOKEN_EXPIRES_IN,
    AUTH_CODE_TTL,
    CLI_TOKEN_HEADER,
    DEFAULT_CONFIG_DIR_PARTS,
    ENV_CONFIG_DIR,
    MCP_CLIENTS_FILENAME,
    REFRESH_TOKEN_PREFIX,
    TOKEN_CACHE_TTL,
    TOKEN_GRACE_TTL,
    TOKEN_VALIDATION_RETRIES,
    TOKEN_VALIDATION_RETRY_DELAY,
    TOKEN_VALIDATION_TIMEOUT,
)


def _clients_file() -> Path:
    config_dir = Path(os.environ.get(ENV_CONFIG_DIR, Path.home().joinpath(*DEFAULT_CONFIG_DIR_PARTS)))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / MCP_CLIENTS_FILENAME


def _load_clients() -> dict[str, OAuthClientInformationFull]:
    try:
        data = json.loads(_clients_file().read_text())
        return {k: OAuthClientInformationFull.model_validate(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001
        return {}


def _save_clients(clients: dict[str, OAuthClientInformationFull]) -> None:
    try:
        _clients_file().write_text(json.dumps({k: v.model_dump(mode="json") for k, v in clients.items()}))
    except Exception:  # noqa: BLE001
        pass


# In-memory stores (single-process only).
_clients: dict[str, OAuthClientInformationFull] = _load_clients()
# internal_state → pending OAuth session metadata
_pending: dict[str, dict] = {}
# authorization_code → CLI token + OAuth metadata
_codes: dict[str, dict] = {}
# sha256(CLI token) → (user_id, monotonic time the backend last confirmed it)
_validated: dict[str, tuple[Optional[str], float]] = {}


class BackendUnavailableError(RuntimeError):
    """The backend could not say whether a token is valid (timeout, 5xx, 429...).

    Raised instead of rejecting the token, so the HTTP layer answers with a server
    error rather than a 401. MCP clients treat a 401 as "credentials revoked" and
    discard them; a 5xx is treated as transient and retried.
    """


class _Verdict(enum.Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


def _token_key(token: str) -> str:
    """Cache key for a token, so raw tokens are not kept as dict keys."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cli_token_from_refresh(refresh_token: str) -> Optional[str]:
    """Return the CLI token wrapped in one of our refresh tokens, else ``None``."""
    if not refresh_token.startswith(REFRESH_TOKEN_PREFIX):
        return None
    return refresh_token[len(REFRESH_TOKEN_PREFIX):] or None


def _token_response(cli_token: str) -> OAuthToken:
    """OAuth token response for a CLI token: short advertised lifetime + refresh token."""
    return OAuthToken(
        access_token=cli_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRES_IN,
        refresh_token=f"{REFRESH_TOKEN_PREFIX}{cli_token}",
    )


# Sentinel returned by ``_resolve_user`` when the backend rejects a token.
_REJECTED = object()


class StobotOAuthProvider(OAuthAuthorizationServerProvider):
    """OAuth AS that bridges FastMCP auth to the stobot CLI token system."""

    def __init__(self, api_url: str, website_url: str, mcp_public_url: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._website_url = website_url.rstrip("/")
        self._mcp_public_url = mcp_public_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # Dynamic client registry                                              #
    # ------------------------------------------------------------------ #

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return _clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _clients[client_info.client_id] = client_info
        _save_clients(_clients)

    # ------------------------------------------------------------------ #
    # Authorization Code flow                                              #
    # ------------------------------------------------------------------ #

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Redirect to the web app's /cli-auth bridge, pointing back to /oauth/callback."""
        internal_state = secrets.token_urlsafe(24)
        _pending[internal_state] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "oauth_state": params.state,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
        }
        callback_url = f"{self._mcp_public_url}/oauth/callback"
        qs = urllib.parse.urlencode({"callback_url": callback_url, "state": internal_state})
        return f"{self._website_url}/cli-auth?{qs}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        entry = _codes.get(authorization_code)
        if not entry:
            return None
        if entry["expires_at"] < time.time():
            _codes.pop(authorization_code, None)
            return None
        if entry["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=entry["scopes"],
            expires_at=entry["expires_at"],
            client_id=entry["client_id"],
            code_challenge=entry["code_challenge"],
            redirect_uri=AnyUrl(entry["redirect_uri"]),
            redirect_uri_provided_explicitly=True,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Return the CLI token as the OAuth access token, plus a refresh token."""
        entry = _codes.pop(authorization_code.code, None)
        if not entry:
            raise TokenError(error="invalid_grant", error_description="Code not found or already used.")
        return _token_response(entry["cli_token"])

    # ------------------------------------------------------------------ #
    # Refresh tokens                                                       #
    # ------------------------------------------------------------------ #
    #
    # The refresh token is ``REFRESH_TOKEN_PREFIX`` + the CLI token, so refreshing is
    # stateless: nothing to persist, nothing lost on restart or redeploy. Refreshing
    # hands back the same CLI token for as long as the backend still accepts it; once
    # the backend revokes or expires it, the refresh fails with ``invalid_grant`` and
    # the client starts a fresh browser login, which is the correct outcome.

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        if _cli_token_from_refresh(refresh_token) is None:
            return None
        return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=[])

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        cli_token = _cli_token_from_refresh(refresh_token.token)
        if cli_token is None:
            raise TokenError(error="invalid_grant", error_description="Unknown refresh token.")
        # Raises BackendUnavailableError (-> HTTP 500, client retries later) when the
        # backend cannot answer and the token has no recent confirmation.
        if await self._resolve_user(cli_token) is _REJECTED:
            raise TokenError(
                error="invalid_grant",
                error_description="The sign-in has been revoked or has expired. Sign in again.",
            )
        return _token_response(cli_token)

    # ------------------------------------------------------------------ #
    # Token verification                                                   #
    # ------------------------------------------------------------------ #

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Validate a bearer token, distinguishing "invalid" from "backend unavailable".

        Returns ``None`` (-> 401) only when the backend definitively rejects the token.
        Raises :class:`BackendUnavailableError` (-> 5xx) when the backend cannot answer
        and the token has not been confirmed within ``TOKEN_GRACE_TTL``.
        """
        if token.startswith(REFRESH_TOKEN_PREFIX):
            return None  # a refresh token is not a bearer credential
        user_id = await self._resolve_user(token)
        if user_id is _REJECTED:
            return None
        return AccessToken(token=token, client_id="", scopes=[], subject=user_id)

    async def _resolve_user(self, token: str) -> "Optional[str] | object":
        """Return the token's user id, or ``_REJECTED`` if the backend refuses it.

        Uses the positive cache, retries transient failures, and falls back to a
        recent confirmation when the backend is unavailable.
        """
        key = _token_key(token)
        now = time.monotonic()
        cached = _validated.get(key)
        if cached and now - cached[1] < TOKEN_CACHE_TTL:
            return cached[0]

        verdict, user_id = await self._validate_with_backend(token)
        for _ in range(TOKEN_VALIDATION_RETRIES):
            if verdict is not _Verdict.UNAVAILABLE:
                break
            await asyncio.sleep(TOKEN_VALIDATION_RETRY_DELAY)
            verdict, user_id = await self._validate_with_backend(token)

        if verdict is _Verdict.VALID:
            _validated[key] = (user_id, time.monotonic())
            return user_id
        if verdict is _Verdict.INVALID:
            _validated.pop(key, None)
            return _REJECTED

        if cached and now - cached[1] < TOKEN_GRACE_TTL:
            _log.warning(
                "Backend unavailable; accepting token last confirmed %.0fs ago (grace %ss).",
                now - cached[1],
                TOKEN_GRACE_TTL,
            )
            return cached[0]
        raise BackendUnavailableError(
            f"Could not validate token: backend {self._api_url} unavailable and no recent confirmation."
        )

    async def _validate_with_backend(self, token: str) -> tuple[_Verdict, Optional[str]]:
        """One ``whoami`` round trip, classified as valid / invalid / unavailable."""
        try:
            async with httpx.AsyncClient(timeout=TOKEN_VALIDATION_TIMEOUT) as http:
                response = await http.get(
                    f"{self._api_url}/v1/cli/auth/whoami",
                    headers={CLI_TOKEN_HEADER: token},
                )
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "Token validation error: could not reach %s/v1/cli/auth/whoami — %s: %s. "
                "Check QSCREENER_API_URL is set correctly.",
                self._api_url,
                type(exc).__name__,
                exc,
            )
            return _Verdict.UNAVAILABLE, None

        if response.status_code == 200:
            try:
                return _Verdict.VALID, response.json().get("user_id")
            except Exception:  # noqa: BLE001
                _log.error("Token validation error: whoami returned a non-JSON 200 body.")
                return _Verdict.UNAVAILABLE, None
        if response.status_code in (401, 403):
            _log.warning("Token validation failed: backend returned %s (token rejected).", response.status_code)
            return _Verdict.INVALID, None
        _log.error(
            "Token validation error: backend returned %s from %s/v1/cli/auth/whoami (treated as unavailable).",
            response.status_code,
            self._api_url,
        )
        return _Verdict.UNAVAILABLE, None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Best-effort revocation via the backend logout endpoint."""
        raw = _cli_token_from_refresh(token.token) or token.token
        _validated.pop(_token_key(raw), None)
        try:
            async with httpx.AsyncClient(timeout=TOKEN_VALIDATION_TIMEOUT) as http:
                await http.post(
                    f"{self._api_url}/v1/cli/auth/logout",
                    headers={CLI_TOKEN_HEADER: raw},
                )
        except Exception:  # noqa: BLE001
            pass


def store_auth_code(internal_state: str, cli_token: str) -> Optional[str]:
    """Consume a pending auth session, store an auth code, and return the redirect URL.

    Called from the ``/oauth/callback`` route handler once the web app delivers
    the CLI token.

    Args:
        internal_state: The CSRF state embedded in the browser redirect URL.
        cli_token: The CLI token delivered by the ``/cli-auth`` web page.

    Returns:
        The redirect URL to send the browser to (client's ``redirect_uri`` with
        ``code`` and ``state`` appended), or ``None`` if the state is unknown.
    """
    pending = _pending.pop(internal_state, None)
    if not pending:
        return None
    code = secrets.token_urlsafe(32)
    _codes[code] = {
        "cli_token": cli_token,
        "client_id": pending["client_id"],
        "redirect_uri": pending["redirect_uri"],
        "code_challenge": pending["code_challenge"],
        "scopes": pending["scopes"],
        "expires_at": time.time() + AUTH_CODE_TTL,
    }
    return construct_redirect_uri(pending["redirect_uri"], code=code, state=pending["oauth_state"])
