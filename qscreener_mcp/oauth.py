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
5. ``load_access_token()`` validates incoming bearer tokens by calling the
   backend ``GET /v1/cli/auth/whoami`` endpoint on every authenticated request.

All state is in-memory; suitable for single-process local and Railway deployments.
"""

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

_AUTH_CODE_TTL = 600  # seconds — codes are exchanged immediately; 10 min is generous


def _clients_file() -> Path:
    config_dir = Path(os.environ.get("QSCREENER_CONFIG_DIR", Path.home() / ".config" / "qscreener"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "mcp_clients.json"


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
        """Return the CLI token as the OAuth access token (no separate token minted)."""
        entry = _codes.pop(authorization_code.code, None)
        if not entry:
            raise TokenError(error="invalid_grant", error_description="Code not found or already used.")
        return OAuthToken(access_token=entry["cli_token"], token_type="Bearer")

    # ------------------------------------------------------------------ #
    # Refresh tokens — not supported (CLI tokens are long-lived)          #
    # ------------------------------------------------------------------ #

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raise TokenError(error="unsupported_grant_type")

    # ------------------------------------------------------------------ #
    # Token verification                                                   #
    # ------------------------------------------------------------------ #

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Validate a bearer token by calling the backend whoami endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.get(
                    f"{self._api_url}/v1/cli/auth/whoami",
                    headers={"X-Stobot-CLI-Token": token},
                )
            if response.status_code != 200:
                _log.warning(
                    "Token validation failed: backend returned %s from %s/v1/cli/auth/whoami",
                    response.status_code,
                    self._api_url,
                )
                return None
            user_id: Optional[str] = response.json().get("user_id")
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "Token validation error: could not reach %s/v1/cli/auth/whoami — %s: %s. "
                "Check QSCREENER_API_URL is set correctly.",
                self._api_url,
                type(exc).__name__,
                exc,
            )
            return None
        return AccessToken(token=token, client_id="", scopes=[], subject=user_id)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Best-effort revocation via the backend logout endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                await http.post(
                    f"{self._api_url}/v1/cli/auth/logout",
                    headers={"X-Stobot-CLI-Token": token.token},
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
        "expires_at": time.time() + _AUTH_CODE_TTL,
    }
    return construct_redirect_uri(pending["redirect_uri"], code=code, state=pending["oauth_state"])
