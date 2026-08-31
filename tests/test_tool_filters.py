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
        # Tool names ``_guard`` was called with, so tests can assert the usage
        # analytics label matches the tool the user actually invoked.
        self.tools: list[str] = []

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

    def put(self, path: str, params: Optional[dict] = None, json: Optional[dict] = None) -> Any:
        """Record a PUT call and return the canned response.

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

        def fake_guard(fn: Any, *, tool: str) -> Any:
            client.tools.append(tool)
            return fn(client)

        monkeypatch.setattr(server, "_guard", fake_guard)
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
    """``screen_share`` posts the normalized config to the public screens endpoint."""
    client = patch_guard({"slug": "AbC1234"})
    server.screen_share(config={"name": "My screen", "groups": []})
    assert client.calls[0]["path"] == "/v1/screens"
    posted = client.calls[0]["json"]["config"]
    assert posted["name"] == "My screen"
    assert posted["groups"] == []
    # Normalization fills the canonical camelCase parameters with their defaults.
    assert posted["winsorizePercentile"] == 5
    assert posted["missingDataPercentile"] == 0.25
    assert posted["normalizeGroupZScores"] is False
    assert posted["includeDuplicatesInScoring"] is False


def test_screen_share_passes_through_on_missing_slug(patch_guard) -> None:
    """If the backend response lacks a slug, the raw response is returned unchanged."""
    raw = {"error": "something went wrong"}
    patch_guard(raw)
    assert server.screen_share(config={"name": "x"}) == raw


def test_screen_share_normalizes_legacy_config(patch_guard) -> None:
    """A legacy/loose config is normalized to camelCase params + nested filters before POST."""
    client = patch_guard({"slug": "AbC1234"})
    server.screen_share(config={
        "name": "Legacy", "groups": [], "winsorize": True, "zScore": True,
        "countries": ["Italy"], "min_market_cap": 1,
    })
    posted = client.calls[0]["json"]["config"]
    assert posted["winsorizePercentile"] == 5
    assert posted["normalizeGroupZScores"] is True
    assert posted["filters"] == {"countries": ["Italy"], "min_market_cap": 1}
    assert "winsorize" not in posted and "zScore" not in posted and "countries" not in posted


def test_systems_create_normalizes_config(patch_guard) -> None:
    """``systems_create`` normalizes the config before posting it."""
    client = patch_guard({"id": 1})
    server.systems_create(name="Sys", config={"name": "Sys", "groups": [], "zScore": True})
    assert client.calls[0]["json"]["config"]["normalizeGroupZScores"] is True


def test_systems_update_omits_config_when_unset(patch_guard) -> None:
    """``systems_update`` without a config must not send a ``config`` key."""
    client = patch_guard({"id": 1})
    server.systems_update(system_id=1, name="Renamed")
    assert "config" not in client.calls[0]["json"]


def test_score_compute_sends_scoring_universe_as_stage_one(patch_guard) -> None:
    """``scoring_universe`` lands in the config, not in the request's result filters.

    The two stages hit different parts of the payload: stage 1 is
    ``score_request.config.scoringUniverseFilters`` (applied before winsorize/z-score),
    stage 2 is the top-level ``filters`` block (applied after). Sending stage 1 to the
    wrong place is the bug quality-screener#194 was opened for.
    """
    client = patch_guard()
    server.score_compute(
        config={"name": "x"},
        scoring_universe={"countries": ["Switzerland"], "sectors": ["Technology"]},
    )
    body = client.calls[0]["json"]
    assert body["score_request"]["config"]["scoringUniverseFilters"] == {
        "countries": ["Switzerland"], "sectors": ["Technology"],
    }
    assert "countries" not in body["filters"]


def test_score_compute_keeps_the_two_stages_separate(patch_guard) -> None:
    """The same filter can be asked as either stage and reaches a different place."""
    client = patch_guard()
    server.score_compute(
        config={"name": "x"},
        scoring_universe={"countries": ["Switzerland"]},
        countries=["Switzerland", "Italy"],
    )
    body = client.calls[0]["json"]
    assert body["score_request"]["config"]["scoringUniverseFilters"]["countries"] == ["Switzerland"]
    assert body["filters"]["countries"] == ["Switzerland", "Italy"]


def test_score_compute_rescales_universe_market_caps_to_billions(patch_guard) -> None:
    """Stage-1 caps are USD in the tool signature and billions in the config block."""
    client = patch_guard()
    server.score_compute(
        config={"name": "x"},
        scoring_universe={"min_market_cap_usd": 5_000_000_000},
    )
    universe = client.calls[0]["json"]["score_request"]["config"]["scoringUniverseFilters"]
    assert universe["min_market_cap"] == 5


def test_score_compute_argument_overrides_universe_in_config(patch_guard) -> None:
    """An explicit ``scoring_universe`` wins over one already carried in the config."""
    client = patch_guard()
    server.score_compute(
        config={"name": "x", "scoringUniverseFilters": {"countries": ["Japan"]}},
        scoring_universe={"countries": ["Germany"]},
    )
    universe = client.calls[0]["json"]["score_request"]["config"]["scoringUniverseFilters"]
    assert universe["countries"] == ["Germany"]


def test_score_compute_rejects_result_filters_in_the_scoring_universe(patch_guard) -> None:
    """Stage-2 keys in stage 1 are an error, not a silent no-op.

    ``min_score`` filters on the scores being computed, so accepting it before scoring
    would be meaningless — the exact silent-wrong-answer failure this split removes.
    """
    client = patch_guard()
    result = server.score_compute(
        config={"name": "x"},
        scoring_universe={"countries": ["Spain"], "min_score": 1.5},
    )
    assert "min_score" in result["error"]
    assert client.calls == []


def test_score_compute_applies_a_saved_screens_filters_as_stage_two(patch_guard) -> None:
    """A saved config's ``filters`` block is inert on this endpoint, so it is forwarded.

    ``CustomScoreConfig`` has no ``filters`` field, so the block would otherwise vanish —
    an agent re-scoring a saved system would silently lose the screen's result filters.
    Config caps are in billions, the request's in USD.
    """
    client = patch_guard()
    server.score_compute(config={
        "name": "x",
        "filters": {"countries": ["France"], "min_score": 1.1, "min_market_cap": 3},
    })
    filters = client.calls[0]["json"]["filters"]
    assert filters["countries"] == ["France"]
    assert filters["min_score"] == 1.1
    assert filters["min_market_cap"] == 3_000_000_000


def test_score_compute_argument_overrides_a_saved_screens_filter(patch_guard) -> None:
    """An explicit stage-2 argument wins over the saved screen's stored value."""
    client = patch_guard()
    server.score_compute(
        config={"name": "x", "filters": {"countries": ["France"]}},
        countries=["Norway"],
    )
    assert client.calls[0]["json"]["filters"]["countries"] == ["Norway"]


def test_score_compute_forwards_regions_as_a_result_filter(patch_guard) -> None:
    """Both stages accept the same keys, so ``regions`` works as a stage-2 filter too."""
    client = patch_guard()
    server.score_compute(config={"name": "x"}, regions=["Europe"])
    assert client.calls[0]["json"]["filters"]["regions"] == ["Europe"]
