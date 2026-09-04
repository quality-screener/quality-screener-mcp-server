# Expose the scoring universe on the MCP surface

- **Type:** enhancement + bug-fix
- **Status:** draft
- **Date:** 2026-08-31
- **Backend counterpart:** `quality-screener/docs/plans/scoring-universe-filters.md`
  (shipped on PR #194, branch `feat/two-stage-scoring-filters`)
- **Repo:** `quality-screener-mcp-server` only. No backend change.

## 1. Why

The backend now has two separately addressable filter stages on `/v1/scores/custom`:

| Stage | Where | Effect |
|---|---|---|
| 1 — scoring universe | `config.scoringUniverseFilters` | applied before winsorize/z-score; **changes every score** |
| 2 — result filters | top-level `filters` | applied after scoring; **never changes a score** |

The MCP server can reach neither correctly:

- `normalize_config()` (`qscreener_mcp/server.py:305`) rebuilds the config from a key
  whitelist, so `scoringUniverseFilters` is **dropped** at all four call sites —
  `score_compute` (:526), `screen_share` (:576), `systems_create` (:684),
  `systems_update` (:703). Stage 1 is unreachable, and an agent that saves or shares a
  screen built with a universe loses it silently. That is the same silent-drop failure
  quality-screener#194 exists to remove, relocated one layer up.
- `config["filters"]` handed to `score_compute` is inert: the backend parses that payload
  as `CustomScoreConfig`, which has no `filters` field. An agent that reads a saved system
  and re-scores it therefore loses the screen's result filters without warning.
- `score_compute`'s docstring (:522) and `README.md:309` both still say a scoring universe
  "does not exist yet" and promise an update when it lands. It landed.

## 2. Goal

Two stages, and only two, expressible over MCP: **score against → filter**. Every filter a
caller can express must land in exactly one stage, and nothing may be silently dropped.

## 3. Steps

1. **`constants.py`** — add `SCORING_UNIVERSE_KEYS` (sectors, industries, regions,
   countries, currencies, exchanges, min_market_cap, max_market_cap) and
   `SCORING_UNIVERSE_CONFIG_KEY = "scoringUniverseFilters"`. Deliberately excludes
   `min_score`/`max_score`/`ticker`/`tickers`: they filter on scores that do not exist yet,
   or select rows.
2. **`normalize_config()`** — carry the universe through on every call site, accepting
   `scoringUniverseFilters` or `scoring_universe_filters`, and rescaling
   `min_market_cap_usd`/`max_market_cap_usd` onto the billions keys exactly as the existing
   `filters` block does. Unknown keys inside the block are dropped, with the stage-2 keys
   called out in the docstring so the split stays legible.
3. **`score_compute(scoring_universe=...)`** — a new first-class parameter, merged into
   `config["scoringUniverseFilters"]`; an explicit parameter wins over a value already in
   the config. Market caps stay `*_usd` per the repo's tool convention.
4. **`score_compute` stops dropping `config["filters"]`** — its result-filter keys are
   folded into the request's top-level stage-2 `filters`, with explicit tool arguments
   winning. This mirrors what the web app does (`fetchScores` passes `config.filters` as
   the request filters) and is what makes "nothing is silently dropped" true.
5. **Docs** — rewrite `score_compute`'s docstring and README §"filters" around the two
   stages, and delete the "not expressible today" paragraphs.
6. **Tests** — `test_config_normalization.py` for the pass-through and rescaling,
   `test_tool_filters.py` for the request shaping and the two-stage split.

## 4. Deliberately not done

- **The `min_market_cap_usd` leak stays.** The flat parameter still floors the scoring
  population as well as the rows (`scores.py` resolves `scoring_min_market_cap_b` from the
  result filters). Neutralizing it at the façade would be business logic; a stage-1
  `min_market_cap_usd` overrides it, and the docstring says so plainly.
- **No population guard.** Deferred on the backend side, so a tiny stage-1 universe still
  returns unstable z-scores over MCP too.
- **`config["filters"]` keeps its persistence meaning** for `screen_share` and the
  `systems_*` tools. Only `score_compute` reinterprets it, because on that endpoint it is
  otherwise inert.

## 5. Release order

The backend must be **deployed** first — PR #194 merged and released. A tool that sends
`scoringUniverseFilters` to an older API is not an error (the field is ignored), but it
silently returns globally-scored numbers, which is exactly the failure this removes.
