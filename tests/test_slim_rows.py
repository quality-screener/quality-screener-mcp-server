"""Tests for MCP payload slimming of score-list responses (_slim_score_rows)."""

from typing import Any

from qscreener_mcp import server


def _score_response() -> dict[str, Any]:
    """Build a backend-shaped score response with embedded duplicate rows.

    Returns:
        A ScoreListResponse-like dict with one keeper row carrying two full
        duplicate rows and a long description.
    """
    long_desc = "x" * 2000
    return {
        "data": [
            {
                "ticker": "GOOGL",
                "score": 1.41,
                "description": long_desc,
                "duplicates": [
                    {"ticker": "GOOG", "score": 1.41, "description": long_desc},
                    {"ticker": "ABEA.DE", "score": 1.40, "description": long_desc},
                ],
            },
            {"ticker": "AAPL", "score": 1.73, "description": "short", "duplicates": None},
        ],
        "pagination": {"total_count": 2},
    }


def test_slim_collapses_duplicates_to_tickers_and_truncates_description() -> None:
    """Default slimming replaces embedded rows with ticker strings and clips descriptions."""
    resp = server._slim_score_rows(_score_response())

    row = resp["data"][0]
    assert row["duplicates"] == ["GOOG", "ABEA.DE"]
    assert len(row["description"]) == server._DESCRIPTION_LIMIT + 1  # + ellipsis
    assert row["description"].endswith("…")
    # short descriptions and None duplicates pass through untouched
    assert resp["data"][1]["description"] == "short"
    assert resp["data"][1]["duplicates"] is None
    # non-row keys untouched
    assert resp["pagination"] == {"total_count": 2}


def test_slim_full_rows_returns_payload_unmodified() -> None:
    """full_rows=True must leave the backend payload byte-identical."""
    original = _score_response()
    resp = server._slim_score_rows(_score_response(), full_rows=True)

    assert resp == original


def test_slim_passes_through_error_and_non_list_payloads() -> None:
    """Error dicts and unexpected shapes are returned untouched."""
    assert server._slim_score_rows({"error": "boom"}) == {"error": "boom"}
    assert server._slim_score_rows({"data": "not-a-list"}) == {"data": "not-a-list"}
    assert server._slim_score_rows(None) is None
