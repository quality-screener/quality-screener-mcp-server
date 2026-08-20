"""Minimal HTTP client for the stobot backend API.

A self-contained copy of the essential parts of ``stobot.cli.client`` with no
dependency on the ``stobot`` package.  Accepts the API base URL and bearer
token as explicit constructor arguments.
"""

from typing import Any, Optional

import httpx

from qscreener_mcp.constants import (
    CLI_TOKEN_HEADER,
    CLIENT_HEADER,
    CLIENT_ID,
    CLIENT_OP_HEADER,
    DEFAULT_TIMEOUT,
    Tool,
)


class ApiError(Exception):
    """A request to the stobot API failed."""


class ApiClient:
    """Thin httpx wrapper that attaches the CLI bearer token to every request."""

    def __init__(
        self,
        api_url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        tool: Optional[Tool] = None,
    ) -> None:
        """Create a client.

        Args:
            api_url: Backend API base URL.
            token: CLI bearer token.
            timeout: Per-request timeout in seconds.
            tool: The MCP tool making the call, reported to the backend for
                usage analytics.
        """
        self._api_url = api_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._tool = tool

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            CLI_TOKEN_HEADER: self._token,
            CLIENT_HEADER: CLIENT_ID,
        }
        if self._tool:
            # StrEnum members are strings, but send the value explicitly so the
            # wire format never depends on the enum's repr.
            headers[CLIENT_OP_HEADER] = str(self._tool)
        return headers

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request and return the decoded JSON body (or ``None`` for empty responses).

        Args:
            method: HTTP method.
            path: Path starting with ``/``.
            **kwargs: Forwarded to httpx (``params``, ``json``, …).

        Raises:
            ApiError: On connection failures or non-2xx responses.
        """
        url = f"{self._api_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as http:
                response = http.request(method, url, headers=self._headers(), **kwargs)
        except httpx.RequestError as exc:
            raise ApiError(f"Could not reach API at {self._api_url}: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else body
            except ValueError:
                detail = response.text
            raise ApiError(f"API error {response.status_code}: {detail}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def get(self, path: str, **kwargs: Any) -> Any:
        """GET request."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """POST request."""
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        """PUT request."""
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """DELETE request."""
        return self.request("DELETE", path, **kwargs)
