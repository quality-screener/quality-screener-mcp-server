---
name: commit-message
description: >
  Craft a high-quality git commit message that follows the Conventional Commits
  specification (https://www.conventionalcommits.org/en/v1.0.0/) and always
  mentions the affected component. Use when the user asks to write a commit
  message, prepare a commit, draft a message for staged changes, or improve an
  existing commit message.
---

# Commit Message Crafter

Produce a single commit message that follows **Conventional Commits 1.0.0** and
**always names the affected component in scope**. This is the only style this
project accepts.

## The Format

```
<type>(<component-scope>): <short imperative summary>

[optional body — why, not what]

[optional footer(s) — breaking changes, refs]
```

Required:

- `<type>` — one of the canonical types below.
- `(<component-scope>)` — **never omit the component scope.** This is the
  project's hard rule on top of Conventional Commits. Pick the smallest
  meaningful scope (see "Choosing the Component Scope").
- `: <short imperative summary>` — ≤ 72 chars, lowercase, imperative mood
  ("add" not "added"/"adds"), no trailing period.

Optional:

- Body separated from the subject by one blank line. Wrap at ~100 chars. Focus
  on **why**, hidden constraints, trade-offs — not a re-statement of the diff.
- Footers separated from the body by one blank line.
- `BREAKING CHANGE: <description>` footer **or** `!` after the type/scope
  (`feat(api)!: ...`) when the change is incompatible.

## Allowed Types

Use exactly one. Order of preference when ambiguous: pick the type that
captures the **user-visible effect**, not the file you touched.

| Type        | Use when                                                                |
|-------------|-------------------------------------------------------------------------|
| `feat`      | A new capability visible to the user, an API, or a developer            |
| `fix`       | A bug fix (regression or pre-existing)                                  |
| `refactor`  | Internal restructuring without behavior change                          |
| `perf`      | Performance-only change                                                 |
| `test`      | Adding or fixing tests only                                             |
| `docs`      | Documentation only (READMEs, CLAUDE.md, comments)                       |
| `style`     | Whitespace / formatting only (rarely needed; ruff/prettier output)      |
| `build`     | Build system, dependency, packaging (`uv`, `npm`, Docker, Alembic env)  |
| `ci`        | CI configuration only                                                   |
| `chore`     | Misc maintenance that doesn't fit elsewhere; **avoid as a catch-all**   |
| `revert`    | Reverts a previous commit; body must reference the SHA being reverted   |

Prefer the specific type over `chore`. If you're tempted to use `chore`, ask
whether `build`, `ci`, `docs`, `refactor`, or `test` actually fits.

## Choosing the Component Scope (REQUIRED)

The component scope is **mandatory**. Pick it by the area touched. Use one
component scope; if the change genuinely spans more than one component, **the
commit should probably be split** (see CLAUDE.md — backend and frontend changes
must be committed separately).

Canonical scopes in this repo:

| Component scope    | Roughly covers                                                   |
|--------------------|------------------------------------------------------------------|
| `api`              | `backend/stobot/api/` routes, dependencies, response shapes      |
| `auth`             | SuperTokens config, session deps, role helpers                   |
| `db`               | SQLModel models, queries, materialized views                     |
| `migrations`       | Alembic migrations                                               |
| `tasks`            | Scheduled jobs (`stobot/tasks.py`), ingestion cadence            |
| `financial`        | FMP client, yfinance, financial data processing                  |
| `analysis`         | Quality scoring, duplicate filtering                             |
| `config`           | `config.py`, `constants.py`, env handling                        |
| `tests`            | Backend pytest changes                                           |
| `ui`               | Anything in `ui/app/` (default frontend scope when narrower      |
|                    | scopes don't fit)                                                |
| `ui-routes`        | Files in `ui/app/routes/`                                        |
| `ui-components`    | Files in `ui/app/components/` (custom, not shadcn primitives)    |
| `ui-auth`          | SuperTokens UI / auth pages                                      |
| `ui-screener`      | Screener-specific UI                                             |
| `ui-portfolio`     | Portfolio-specific UI                                            |
| `docs`             | `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md`                   |
| `docker`           | `docker-compose.yml`, Dockerfiles                                |
| `deps`             | Dependency bumps (`pyproject.toml`, `package.json`)              |
| `ci`               | CI workflow files                                                |
| `skills`           | Files under `.claude/skills/`                                    |

If the natural component is not in the table, invent one that is short,
lowercase, kebab-cased, and matches the directory or feature name. Be
consistent across commits.

## Subject Line Rules

- Imperative mood: "add", "fix", "rename", "remove" — not "adds", "added",
  "adding".
- Lowercase first character (after the colon).
- No trailing period.
- ≤ 72 characters total including type and scope.
- Reference the user-visible effect or the specific thing that changed, not the
  ticket number (put refs in the footer).
- Don't restate the type ("fix(api): fix bug in users endpoint" → "fix(api):
  return 404 when user id is missing").

## Body Rules (Optional but Encouraged)

Use a body when **any** of these apply:

- The change has a non-obvious reason (workaround, constraint, incident).
- The change has trade-offs the next reader needs.
- The change is invisible in the diff (e.g., it disables a feature flag).
- The change is a breaking change.

In the body, focus on **WHY**: motivation, alternative considered, side
effects, references to incidents, links to research. Do not narrate the diff
("changed X to Y in file Z") — the diff already does that.

Wrap lines at ~100 characters.

## Footer Rules

- `BREAKING CHANGE: <what breaks and how to migrate>` — must appear when the
  change is incompatible.
- `Refs: #123` / `Closes: #123` — link to the issue or PR.
- `Co-authored-by: Name <email>` when applicable.

## Workflow When Generating a Message

1. **Look at staged changes.** Run `git status` and `git diff --staged` (or
   `--cached`). If nothing is staged, ask the user before staging anything.
2. **Detect the component** from the file paths. If staged files cross
   components (e.g., `backend/` *and* `ui/`), STOP — split the commit per
   CLAUDE.md before drafting a message.
3. **Detect the type** from the user-visible effect. Use the table above.
4. **Pick the smallest meaningful scope** (single component).
5. **Draft the subject** in imperative mood, ≤ 72 chars.
6. **Add a body** if any of the "when to use body" conditions apply.
7. **Add `BREAKING CHANGE:`** if the public surface changes incompatibly.
8. **Show the user the message and the suggested `git commit -m` command**;
   do not run the commit yourself unless explicitly told to.

## Examples

### Simple bug fix

```
fix(api): return 404 when user id is missing from session
```

### Feature with body

```
feat(ui-screener): add sector filter to the screener table

The screener now exposes a multi-select sector filter sourced from the
materialized view aggregation, so users can narrow scans without going
back to the all-tickers view.
```

### Refactor, no behavior change

```
refactor(analysis): extract quality_score helpers into separate module
```

### Performance change

```
perf(db): batch financials fetch via selectinload to avoid N+1 on /screener
```

### Test-only change

```
test(financial): add coverage for FMP retry/backoff path
```

### Documentation-only change

```
docs(skills): document the new backend-development skill
```

### Dependency bump

```
build(deps): bump fastapi to 0.115.0
```

### Breaking change (footer style)

```
feat(api): rename /v1/users to /v1/profile

BREAKING CHANGE: clients calling /v1/users must migrate to /v1/profile.
The old route returns 410 Gone for one release cycle.
```

### Breaking change (! shorthand)

```
feat(auth)!: require email verification before issuing session tokens

Sessions for unverified users are now refused with 403. Sign-up flow must
call /v1/auth/verify-email before /v1/auth/session.
```

### Revert

```
revert(tasks): revert "feat(tasks): refresh materialized views hourly"

Reverts c2c9216. The hourly cadence increased Postgres CPU above
the soft-launch budget; reverting to daily until we tune the index.
```

## Anti-Patterns (Reject and Rewrite)

- `chore: update stuff`
- `fix: bug` — no scope, no detail
- `feat: add new feature for users`  — no scope; "new feature" is redundant
- `Update README.md` — no type, no scope, capitalized, past-tense-ish
- `feat(api): added new endpoint.` — past tense, trailing period
- Subjects > 72 chars; multi-paragraph subjects
- Mixing types: "feat(api): fix and add" — split into two commits
- Mixing components: "feat(api,ui): add screener filter" — split into two
  commits (CLAUDE.md mandates separate FE/BE commits)

## Final Self-Check

Before delivering a message, verify:

- [ ] Type is one of the canonical types and matches the user-visible effect
- [ ] Scope names a component, not a file
- [ ] Subject is lowercase, imperative, ≤ 72 chars, no trailing period
- [ ] Body (if present) explains WHY, not WHAT
- [ ] Breaking changes are flagged via `!` or `BREAKING CHANGE:`
- [ ] If the diff spans both backend and frontend, the user has been told to
      split the commit
