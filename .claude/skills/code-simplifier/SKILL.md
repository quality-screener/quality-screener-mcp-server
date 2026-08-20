---
name: code-simplifier-backend
description: >
  Simplify Python backend code for clarity, maintainability, and correctness while
  preserving behavior. Use when asked to "simplify the backend", "clean up Python
  code", "refactor for clarity", "reduce complexity", "remove dead code", or review
  recently modified backend code for elegance. Targets FastAPI routes, service-layer
  code, scheduled jobs, database queries, and Pydantic / SQLModel boundaries.
---

# Backend Code Simplifier

Expert simplification of Python backend code. Make the code **easier to read,
safer to evolve, and more consistent** with project standards — without changing
observable behavior.

## Core Goal

**Preserve functionality exactly while reducing accidental complexity.**

Prefer explicit, boring, maintainable Python over clever or overly compact code.
A few extra lines that read top-to-bottom are almost always better than a dense
expression that requires a debugger to understand.

## Mental Model — "Make It Boring"

When in doubt, ask:

1. **Can a new reader summarize this function in one sentence?** If not, split it.
2. **Does the happy path read top-to-bottom without diving into branches?** If
   not, hoist guard clauses and flatten nesting.
3. **Is every name a noun for data, a verb for action?** If not, rename.
4. **Does the abstraction earn its keep at this call site count?** If only one
   caller uses it, inline it. If three+ callers use a near-duplicate, extract it.
5. **Could you delete this code and still pass the tests?** If yes, delete it.

## Project Standards (Non-negotiable)

- Keep full type annotations on functions; do not drop them to "simplify".
- Keep Google-style docstrings where the codebase has them.
- Respect existing service-layer and module boundaries (`api/`, `analysis/`,
  `financial/`, `database/`).
- **Reuse existing helpers and patterns before introducing new abstractions.**
- Reuse `research/` prototypes when the simplification target maps to one.
- Keep changes pytest-friendly; do not break fixtures or test seams.
- Do not run `ruff` or type checking unless the user explicitly asks.

## Simplification Priorities (In Order)

### 1. Preserve Behavior — Always

Do not change API contracts, database semantics, scheduling cadence, auth
behavior, numerical/financial logic, or response shapes unless the user asks
for a behavioral change. When uncertain, ask before editing.

### 2. Reduce Complexity

- Flatten deeply nested conditionals; prefer guard clauses and `return` early.
- Replace "do everything" functions with smaller helpers — but only when the
  split is **natural** (one clear noun/verb each), not just to lower line counts.
- Remove duplicated logic; consolidate near-duplicate branches.
- Eliminate one-use abstractions, pass-through wrappers, and needless indirection.
- Replace boolean-flag pyramids with explicit control flow or enum dispatch.
- Break apart dense comprehensions / chained expressions when readability suffers.
- Prefer table-driven dispatch (dict / match) over long `if/elif` ladders.

### 3. Remove Dead Weight (Conservatively)

Look for:

- Unused imports, variables, parameters, constants, private helpers
- Functions or branches that nothing references
- Stale compatibility shims, commented-out code, obsolete TODOs
- Fallback branches that can never execute given current callers

Only remove dead code when usage is **clearly** absent from the relevant
codebase context. When in doubt, flag instead of delete — the cost of a wrong
deletion in the data pipeline is high.

### 4. Enforce Python Best Practices

Prefer:

- Clear names over abbreviations
- `is None` / `is not None` for nullability (don't conflate with falsey values)
- Context managers (`with`) for resources
- Established project models (Pydantic / SQLModel / dataclass) over raw dicts
- Standard library utilities (`itertools`, `functools`, `pathlib`) when clearer
- Explicit exceptions over silent failure
- Small, focused functions with a single clear responsibility
- `match` statements for closed enum-like dispatch (Python 3.10+)

Avoid:

- Broad `except Exception` without strong justification or re-raising
- Mutable default arguments (`def f(x=[]):`)
- Hidden side effects during imports
- Boolean-trap APIs (multiple positional flags)
- Reassigning a variable to mean something different mid-function
- Dense one-liners that defeat debuggers

## Backend Smell Checklist

Review for these patterns:

### Control Flow
- Functions with too many branches or deeply nested logic
- Repeated `if/elif` trees that should be table-driven
- Early validation mixed with persistence, logging, formatting, and response
  shaping in one function
- Retry/fallback logic inlined instead of isolated in a helper

### Data / Models
- Raw dicts passed around when typed models exist
- Repeated key lookups into nested JSON blobs without normalization
- Conversions between similar shapes multiple times in one flow
- Magic strings for field names, statuses, source identifiers — should be
  centralized in `constants.py` or an enum

### FastAPI / Service Layer
- Route handlers containing business logic, query composition, and response
  shaping all at once — split into a service call
- Dependency acquisition inlined instead of through `Depends`
- HTTP concerns (HTTPException, status codes) leaking into lower-level services
- Services returning shapes that force repeated cleanup in callers
- Repeated pagination, filtering, or error mapping across endpoints — extract

### Error Handling
- Catching too early and hiding context
- Returning `None`/empty when a typed result/error path would be clearer
- Logging and re-raising the same exception multiple times
- Using exceptions for normal control flow where branching would do

### Database / I/O
- Repeated queries / I/O setup that can be centralized in `queries.py`
- Large functions that mix fetching, transforming, and persisting
- Inline SQL fragments duplicated across modules
- Serialization/deserialization repeated instead of wrapped once
- N+1 queries — push eager loading or batched fetch into the service layer

### Drift / Dead Code
- Parameters kept only for historical reasons
- Fallback branches for providers (FMP, Yahoo) no longer used
- Helpers that mirror library behavior with no extra value
- Code paths guarded by constants that never vary

## Complexity Heuristics — Strong Signals

Treat these as **definitely simplify**:

- A function is hard to summarize in one sentence
- A function mixes validation, transformation, persistence, and presentation
- A reader must track too many temporary variables at once
- Similar logic appears in 2+ places with minor differences
- The happy path is buried under exception handling
- A nested `if` block is more than 3 levels deep

## Refinement Process

1. **Identify target scope** — usually recently modified backend code, unless
   the user asks for broader review.
2. **Read surrounding modules** so you follow existing architecture instead of
   inventing a new one. Look for an existing helper before writing a new one.
3. **Check `research/`** for relevant prototypes — those implementations
   often already encode the simpler form.
4. **Categorize issues** — complexity, dead code, best-practice violation,
   smell, naming, error handling.
5. **Simplify highest-value issues first.** A 50-line function collapsing to
   20 lines beats five micro-style nits.
6. **Keep changes incremental and reviewable.** One concept per commit.
7. **Verify behavior** — interfaces, contracts, and data shapes intact.
8. **Flag uncertainty** — don't delete code on speculation; call it out.

## Decision Rules

- Prefer a small helper over another nested branch — **only if it has a name**.
- Prefer a direct expression over a trivial wrapper.
- Prefer named intermediate variables when they explain intent (`market_cap_usd`
  beats a chained expression).
- Prefer existing project patterns over generic textbook patterns.
- Prefer removing code over abstracting it when the code adds no value.
- Prefer leaving potentially-used code in place when evidence is inconclusive.

## Do Not Over-Simplify

- Do not collapse meaningful domain concepts into generic helpers.
- Do not merge unrelated responsibilities to reduce line count.
- Do not replace readable multi-step logic with clever comprehensions or
  metaprogramming.
- Do not remove defensive checks at **external data boundaries** (Yahoo / FMP
  responses, user input) — these protect the pipeline.
- Do not delete code that may be used dynamically (e.g., reflection, importlib,
  Alembic migrations) without strong evidence.

## Example Improvements

### Before — Mixed responsibilities

```python
def build_company_payload(raw: dict[str, Any], session: Session) -> dict[str, Any]:
    if not raw:
        return {}

    ticker = raw.get("symbol")
    if not ticker:
        logger.warning("missing symbol")
        return {}

    company = session.exec(select(Company).where(Company.ticker == ticker)).first()
    if company is None:
        company = Company(ticker=ticker)
        session.add(company)

    name = raw.get("longName") or raw.get("shortName") or ""
    company.name = name.strip()
    session.commit()

    return {"ticker": company.ticker, "name": company.name}
```

### After — Clear flow

```python
def build_company_payload(raw: dict[str, Any], session: Session) -> dict[str, Any]:
    ticker = extract_ticker(raw)
    if ticker is None:
        return {}

    company = get_or_create_company(session, ticker)
    company.name = extract_company_name(raw)
    session.commit()

    return {"ticker": company.ticker, "name": company.name}
```

### Before — Falsey bug risk

```python
if not market_cap:
    return None
```

### After — Precise intent

```python
if market_cap is None:
    return None
```

### Before — Dead wrapper

```python
def has_items(values: list[str]) -> bool:
    return len(values) > 0

if has_items(values):
    ...
```

### After — Inline usage

```python
if values:
    ...
```

### Before — Long if/elif ladder

```python
def adjust_currency(ticker: str, amount: float) -> float:
    if ticker.endswith(".L"):
        return amount / 100
    elif ticker.endswith(".HK"):
        return amount * 1.0
    elif ticker.endswith(".AX"):
        return amount * 0.7
    ...
```

### After — Table-driven

```python
CURRENCY_ADJUSTMENTS: dict[str, float] = {
    ".L": 1 / 100,
    ".HK": 1.0,
    ".AX": 0.7,
}

def adjust_currency(ticker: str, amount: float) -> float:
    suffix = next((s for s in CURRENCY_ADJUSTMENTS if ticker.endswith(s)), None)
    return amount * CURRENCY_ADJUSTMENTS[suffix] if suffix else amount
```

## Expected Output Style

When **reviewing** code, explain:

- What is unnecessarily complex and why
- What appears unused or dead
- Which Python / backend best practice is being violated
- The safest simplification (with a short example if non-obvious)
- Any uncertainty that requires caution

When **editing** code, keep changes focused, reviewable, and one-concept-per-edit.
Always run the relevant pytest after edits and report results.
