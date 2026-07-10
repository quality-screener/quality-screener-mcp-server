"""Tests for ``normalize_config`` — reshaping loose configs onto the backend contract."""

from qscreener_mcp import server


def _groups() -> list:
    """Return a minimal valid list of metric groups."""
    return [{"id": "returns", "name": "Returns", "weight": 1.0,
             "metrics": [{"id": "roe", "name": "ROE", "weight": 1.0}]}]


def test_legacy_boolean_flags_map_to_canonical_parameters() -> None:
    """The legacy ``winsorize``/``zScore`` booleans map onto camelCase parameters."""
    out = server.normalize_config({"name": "S", "groups": _groups(), "winsorize": True, "zScore": True})
    assert out["winsorizePercentile"] == 5
    assert out["normalizeGroupZScores"] is True
    assert "winsorize" not in out
    assert "zScore" not in out


def test_snake_case_parameters_become_camel_case() -> None:
    """snake_case scoring parameters are emitted as camelCase."""
    out = server.normalize_config({
        "name": "S", "groups": _groups(),
        "winsorize_percentile": 7, "missing_data_percentile": 0.3,
        "normalize_group_z_scores": True, "include_duplicates_in_scoring": True,
    })
    assert out["winsorizePercentile"] == 7
    assert out["missingDataPercentile"] == 0.3
    assert out["normalizeGroupZScores"] is True
    assert out["includeDuplicatesInScoring"] is True


def test_top_level_filters_are_hoisted_into_nested_block() -> None:
    """Filter keys placed at the top level are folded into a nested ``filters`` block."""
    out = server.normalize_config({
        "name": "S", "groups": _groups(),
        "countries": ["Italy"], "sectors": ["Technology"], "min_market_cap": 1,
    })
    assert out["filters"] == {"countries": ["Italy"], "sectors": ["Technology"], "min_market_cap": 1}
    assert "countries" not in out
    assert "sectors" not in out


def test_nested_filter_wins_over_top_level_duplicate() -> None:
    """A key present both nested and at top level keeps the nested value."""
    out = server.normalize_config({
        "name": "S", "groups": _groups(),
        "sectors": ["Energy"], "filters": {"sectors": ["Technology"]},
    })
    assert out["filters"]["sectors"] == ["Technology"]


def test_defaults_filled_when_parameters_missing() -> None:
    """A config with only groups gets canonical parameter defaults and a default name."""
    out = server.normalize_config({"groups": _groups()})
    assert out["name"] == "Custom Screen"
    assert out["winsorizePercentile"] == 5
    assert out["missingDataPercentile"] == 0.25
    assert out["normalizeGroupZScores"] is False
    assert out["includeDuplicatesInScoring"] is False


def test_no_filters_produces_no_filters_key() -> None:
    """A config without any filters must not emit a ``filters`` key."""
    out = server.normalize_config({"name": "S", "groups": _groups()})
    assert "filters" not in out


def test_groups_pass_through_unchanged() -> None:
    """Metric groups are forwarded verbatim (backend validates their content)."""
    groups = _groups()
    out = server.normalize_config({"name": "S", "groups": groups})
    assert out["groups"] == groups


def test_out_of_range_winsorize_falls_back_to_default() -> None:
    """An out-of-range winsorize value falls back to the default percentile."""
    assert server.normalize_config({"name": "S", "groups": _groups(), "winsorizePercentile": 99})[
        "winsorizePercentile"
    ] == 5


def test_canonical_config_is_preserved() -> None:
    """A config already in canonical shape is returned unchanged."""
    canonical = {
        "name": "S", "winsorizePercentile": 5, "missingDataPercentile": 0.25,
        "normalizeGroupZScores": True, "includeDuplicatesInScoring": False,
        "groups": _groups(), "filters": {"countries": ["Italy"]},
    }
    assert server.normalize_config(canonical) == canonical
