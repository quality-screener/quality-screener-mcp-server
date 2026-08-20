---
name: new-feature
description: >
  Plan and prepare a new feature end-to-end. Use when the user asks to "add a
  new feature", "design X", "let's build Y", "plan a feature", or "prepare a
  feature plan". Enforces the project flow: check prior plans in `docs/plans`,
  classify the feature type, split cleanly between backend and frontend, get
  user approval, then save the plan as Markdown under `docs/plans/`.
---

# New Feature Planner

Produce a solid, reviewable implementation plan **before** any code is written.
A plan that survives 10 minutes of review saves 10 hours of rework.

## The Flow (Non-Negotiable)

Always follow these steps **in order**.

### Step 1 — Search `docs/plans/` for related prior work

`docs/plans/` is the canonical archive of every feature plan written for this
project. Before designing anything:

1. List `docs/plans/` (`ls docs/plans/`).
2. Skim filenames; open anything whose name overlaps with the request.
3. Grep the folder for relevant keywords (feature name, domain term, ticker,
   route, etc.):
   `grep -r -l "<keyword>" docs/plans/`.
4. Read related plans end-to-end. Look specifically for:
   - Architectural decisions that constrain the new plan
   - Patterns the project has already adopted (reuse them)
   - Lessons learned / what didn't work
   - Open follow-ups that this feature might pick up

**Tell the user what you found**, including "nothing relevant" if that's the
honest answer. Cite the plan filename you took inspiration from in the new plan.

If the feature also relates to the **research/** prototypes (data fetching,
scoring, helpers), check there too — the implementation pattern usually
already exists.

### Step 2 — Classify the feature type

Identify what kind of change this is, because the plan structure and the set
of related prior plans depend on it. Use one of:

| Type             | Description                                                            |
|------------------|------------------------------------------------------------------------|
| `enhancement`    | Adds a new user-visible capability to an existing feature              |
| `new-capability` | Wholly new feature area (new domain, new page, new pipeline)           |
| `refactoring`    | Internal restructuring without behavior change                         |
| `performance`    | Targeted performance work with measurable goals                        |
| `bug-fix`        | Non-trivial bug fix that needs design (small fixes don't need a plan)  |
| `test`           | Adding meaningful test coverage (e.g., correctness suite)              |
| `infrastructure` | Docker, CI, deployment, environment, secrets management                |
| `ux`             | UX redesign or audit follow-up                                         |
| `security`       | Security hardening (auth, input validation, secrets, rate limits)      |

State the type explicitly at the top of the plan. This makes it easy to find
related plans later via grep.

### Step 3 — Draft the plan with a CLEAN backend ↔ frontend split

Every plan must contain two **independent** implementation tracks:

- **Backend track** — database, API, services, scheduled jobs, auth, tests
- **Frontend track** — routes, components, state, data fetching, UX, tests

Both tracks must be implementable on their own. The backend track is delivered
first (per CLAUDE.md), tested end-to-end via docker-compose, and only then does
the frontend track start. The plan must reflect this ordering. If a feature is
purely backend or purely frontend, say so explicitly and omit the other track.

The contract between tracks (API endpoints, payload shapes, status codes,
errors) is fixed in the **backend track** and the frontend track consumes it.
List the exact API surface in the plan so the frontend track can mock it.

### Step 4 — Get user approval, then save

After drafting the plan in chat:

1. Show the plan to the user.
2. Ask for explicit approval (or iterate on feedback).
3. **Only after acceptance**, save it as Markdown under
   `docs/plans/<kebab-case-name>.md`.
4. Confirm the saved path to the user.

Do not start coding before the plan is saved. Do not save the plan before
approval.

## Plan Template

Use this exact structure. Adapt headings only when a section is genuinely N/A.

```markdown
# <Feature Title>

- **Type:** <enhancement | new-capability | refactoring | performance | bug-fix | test | infrastructure | ux | security>
- **Status:** draft
- **Date:** <YYYY-MM-DD>
- **Related plans:** <list filenames in docs/plans/ or "none">
- **Related research:** <list files in research/ or "none">

## 1. Motivation

Why are we doing this? Who benefits? What pain does it remove? Link to issues
/ incidents / Slack threads if applicable.

## 2. Goals & Non-goals

- **Goals:** Concrete, verifiable outcomes.
- **Non-goals:** Things we're explicitly NOT doing in this plan.

## 3. User-visible behavior

Describe the feature from the user's perspective. Include happy path and the
top 2–3 edge cases the user might hit.

## 4. Architecture overview

A short narrative + ASCII or bullet diagram showing the components touched
and the direction of data flow.

## 5. Backend track

### 5.1 Data model
- New tables / columns / indexes
- Migration plan (Alembic revision)
- JSONB field shapes if applicable

### 5.2 API contract
- Endpoints (method, path, request, response, errors)
- Auth requirements (SuperTokens session, roles)
- Pagination / filtering / sorting rules

### 5.3 Services
- New / changed modules in `backend/stobot/`
- Reuse-first list: existing helpers and `research/` files to follow

### 5.4 Scheduled jobs / materialized views
- New tasks added to `tasks.py`, cadence, idempotency
- View refresh implications

### 5.5 Tests (mandatory)
- Unit tests to add (file paths, scenarios)
- Correctness tests for large changes (data pipeline integrity, scoring,
  duplicate detection, FX, etc.)
- Run command: `cd backend && uv run pytest`

### 5.6 Verification via docker-compose
- Exact requests / queries to run against the live stack on `:8001` /
  Postgres after the change

## 6. Frontend track

(Skip this section if the feature is backend-only. Otherwise it must come
**after** the backend is fully functional.)

### 6.1 Routes & pages
- React Router routes added or changed (file paths in `ui/app/routes/`)

### 6.2 Components
- New components (location, props, parent)
- **Simplicity check:** which existing component is being extended instead?
- Shared state introduced (if any) — justify why local state isn't enough

### 6.3 Data layer
- TanStack Query keys, fetchers, mutations
- Loader / RSC usage
- Optimistic updates

### 6.4 UX
- Empty / loading / error states
- Accessibility considerations (labels, focus, ARIA)
- Mobile / responsive behavior

### 6.5 Tests
- Component / hook tests (Vitest + Testing Library)
- Playwright MCP verification steps (golden path + edge cases)

## 7. Rollout

- Feature flags? Migration ordering? Backfill?
- Order of commits (backend first; backend and frontend always in separate
  commits per CLAUDE.md).

## 8. Risks & open questions

- What could break (data, performance, UX)?
- What do we not know yet?
- What needs the user's explicit decision before coding starts?

## 9. References

- Prior `docs/plans/` files relied on
- `research/` prototypes
- External docs (FastAPI, React, Vercel, etc.)
```

## Critical Practices

Beyond the flow above, every solid plan should:

1. **Be reuse-first.** Before proposing a new module, name the existing one to
   extend. Before a new component, name the existing one to compose.
2. **Specify the API contract precisely.** Path, verb, request body, response
   body, status codes, error envelope, auth header expectation. Imprecise
   contracts cause backend ↔ frontend drift.
3. **Identify migrations explicitly.** Every schema change names the Alembic
   revision file and notes whether the migration is forward-only.
4. **Include the test list in the plan.** "Add tests" is not a plan. List
   files, scenarios, and which run against the docker-compose stack.
5. **Call out scheduled-job interactions.** A new field or table that affects
   `tasks.py` or materialized views must be flagged — silent breakage of the
   nightly job is the most expensive failure mode.
6. **Anticipate the rollback.** If something goes wrong after deploy, what's
   the revert path? Migrations need a down-revision or a documented manual fix.
7. **Bound the scope.** Goals and non-goals are the strongest tool against
   scope creep mid-implementation.
8. **List explicit user decisions needed.** If you'd otherwise guess on a
   product question, the plan should ask the user first.
9. **Estimate complexity.** A short note on whether this is small / medium /
   large. Large features must run the correctness tests per
   `backend-development`.
10. **Reference the simplicity tenet for UI work.** Any frontend addition must
    pass the components / props / shared-state simplicity check from
    `frontend-development`.

## Anti-Patterns

- Writing code before the plan is approved and saved
- Mixing backend and frontend implementation steps in a single track
- "We'll figure out the API later" — define it up front
- Plans that never get saved to `docs/plans/`
- Plans that don't cite prior `docs/plans/` files even when relevant ones exist
- Plans that omit tests
- Plans that say "TBD" for migration or rollout strategy on schema changes

## Final Self-Check (Before Saving)

- [ ] I searched `docs/plans/` and named what I found (including "nothing")
- [ ] I checked `research/` for prototype implementations of related logic
- [ ] I classified the feature type
- [ ] The backend and frontend tracks are independently implementable
- [ ] The API contract is fully specified
- [ ] Tests (unit + correctness for large changes) are listed by file/scenario
- [ ] Docker-compose verification steps are listed
- [ ] User has explicitly approved the plan
- [ ] File saved to `docs/plans/<kebab-case-name>.md` and path confirmed
