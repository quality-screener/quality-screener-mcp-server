"""Tests for filter forwarding and the screen-sharing tool in the MCP server."""

from typing import Any, Optional

import pytest

from qscreener_mcp import server


class _RecordingClient:
    """Fake ApiClient that records the last request and returns a canned body."""

    def __init__(self, response: Any = None) -> None:
        """Store the canned response and prepare a capture slot.

        Args:
            response: Value returned from ``post``; defaults to an empty dict.
        """
        self.response = {} if response is None else response
        self.calls: list[dict[str, Any]] = []

    def post(self, path: str, params: Optional[dict] = None, json: Optional[dict] = None) -> Any:
        """Record a POST call and return the canned response.

        Args:
            path: Request path.
            params: Query-string parameters.
            json: JSON request body.

        Returns:
            The canned response supplied at construction time.
        """
        self.calls.append({"path": path, "params": params, "json": json})
        return self.response


@pytest.fixture
def patch_guard(monkeypatch: pytest.MonkeyPatch):
    """Bypass authentication by invoking the guarded callable with a fake client.

    Args:
        monkeypatch: pytest fixture used to replace ``server._guard``.

    Returns:
        A factory that installs a ``_RecordingClient`` and returns it.
    """
    def install(response: Any = None) -> _RecordingClient:
        client = _RecordingClient(response)
        monkeypatch.setattr(server, "_guard", lambda fn: fn(client))
        return client

    return install


def test_score_compute_forwards_countries(patch_guard) -> None:
    """``score_compute`` forwards the ``countries`` filter to the custom-score endpoint."""
    client = patch_guard()
    server.score_compute(config={"name": "x"}, countries=["United States", "Japan"])
    assert client.calls[0]["json"]["filters"]["countries"] == ["United States", "Japan"]


def test_score_compute_forwards_all_categorical_filters(patch_guard) -> None:
    """``score_compute`` forwards every categorical universe filter, not just sectors."""
    client = patch_guard()
    server.score_compute(
        config={"name": "x"},
        sectors=["Technology"],
        industries=["Software"],
        countries=["Germany"],
        currencies=["EUR"],
        exchanges=["XETRA"],
    )
    filters = client.calls[0]["json"]["filters"]
    assert filters["sectors"] == ["Technology"]
    assert filters["industries"] == ["Software"]
    assert filters["countries"] == ["Germany"]
    assert filters["currencies"] == ["EUR"]
    assert filters["exchanges"] == ["XETRA"]


def test_score_compute_omits_unset_filters(patch_guard) -> None:
    """Unset filters are not sent, so the backend treats the universe as unfiltered."""
    client = patch_guard()
    server.score_compute(config={"name": "x"})
    assert "countries" not in client.calls[0]["json"]["filters"]


def test_scores_for_tickers_posts_upper_cased_tickers(patch_guard) -> None:
    """``scores_for_tickers`` upper-cases tickers and posts them to the by-tickers endpoint."""
    client = patch_guard({"data": []})
    server.scores_for_tickers(tickers=["aapl", "Msft"])
    assert client.calls[0]["path"] == "/v1/scores/by-tickers"
    assert client.calls[0]["json"]["tickers"] == ["AAPL", "MSFT"]


def test_scores_for_tickers_forwards_scoring_system_id(patch_guard) -> None:
    """A supplied scoring system id is forwarded in the request body."""
    client = patch_guard({"data": []})
    server.scores_for_tickers(tickers=["AAPL"], scoring_system_id=12)
    assert client.calls[0]["json"]["scoring_system_id"] == 12


def test_scores_for_tickers_omits_scoring_system_id_when_unset(patch_guard) -> None:
    """When no scoring system is given, the key is omitted (default scoring)."""
    client = patch_guard({"data": []})
    server.scores_for_tickers(tickers=["AAPL"])
    assert "scoring_system_id" not in client.calls[0]["json"]


def test_screen_share_builds_full_url(monkeypatch: pytest.MonkeyPatch, patch_guard) -> None:
    """``screen_share`` returns a copy-pasteable URL derived from the website base URL."""
    monkeypatch.setattr(server, "_WEBSITE_URL", "https://app.example.com")
    patch_guard({"slug": "AbC1234", "created": True, "view_count": 0})
    result = server.screen_share(config={"name": "My screen"})
    assert result["url"] == "https://app.example.com/s/AbC1234"
    assert result["slug"] == "AbC1234"
    assert result["created"] is True
    assert result["view_count"] == 0


def test_screen_share_posts_config(patch_guard) -> None:
    """``screen_share`` posts the config to the public screens endpoint."""
    client = patch_guard({"slug": "AbC1234"})
    server.screen_share(config={"name": "My screen", "groups": []})
    assert client.calls[0]["path"] == "/v1/screens"
    assert client.calls[0]["json"] == {"config": {"name": "My screen", "groups": []}}


def test_screen_share_passes_through_on_missing_slug(patch_guard) -> None:
    """If the backend response lacks a slug, the raw response is returned unchanged."""
    raw = {"error": "something went wrong"}
    patch_guard(raw)
    assert server.screen_share(config={"name": "x"}) == raw
