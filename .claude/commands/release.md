---
description: Cut a new release — bump the version on main, tag it, and publish a GitHub release
argument-hint: "[patch|minor|major]"
allowed-tools: Bash, Read, Edit
---

Cut a new release for `qscreener-mcp`. The bump type is `$1` (default to `patch` if empty).

## Critical rules

- **`pyproject.toml` and `server.json` versions MUST stay in sync** with each other and with the git tag. The package exposes `__version__` via `importlib.metadata` (see `qscreener_mcp/__init__.py`), and it is sent to the backend as `CLIENT_ID = f"mcp/{__version__}"` — a stale `pyproject.toml` version silently corrupts usage analytics.
- Git tags use a `v` prefix (e.g. `v0.2.0`); the `version` fields in `pyproject.toml` and `server.json` do NOT (e.g. `0.2.0`).
- Releases are cut **directly on `main`** — this repo has no `develop` branch and `main` is not protected. Do not open a release PR.
- Never push or tag until the version edits are committed.
- **The agent never pushes to `main`.** Commit and tag locally, then stop and hand off — the user runs the actual `git push` themselves. This mirrors the `quality-screener` release process, where the agent opens the release PR but leaves merging (and thus the push to `main`) to the user.

## Steps

1. **Sync `main`.** (Do this FIRST, before any edits.)
   - `git fetch origin --tags`
   - `git switch main && git pull --ff-only origin main`
   - Confirm the working tree is clean (`git status --porcelain` returns nothing). Abort and tell the user if it is not.

2. **Determine the new version.**
   - Run `git tag --sort=-v:refname | head -5` to find the latest tag.
   - If tags exist: parse the latest semver tag (strip the `v` prefix) and bump according to `$1`:
     - `patch` (default) → `X.Y.(Z+1)`
     - `minor` → `X.(Y+1).0`
     - `major` → `(X+1).0.0`
   - If **no tags exist** (first release): do not bump. Use the version already in `pyproject.toml` as-is, and say so in the final report.
   - Call the new version `NEW` (no `v`) and the tag `vNEW`.
   - Sanity check that `vNEW` does not already exist: `git rev-parse -q --verify refs/tags/vNEW` must fail.

3. **Update the version manifests** to `NEW`:
   - Edit `version` in `pyproject.toml` (`[project]` section).
   - Edit `version` in `server.json` (top level).
   - Confirm both now read exactly `NEW`: `grep -n '"\?version"\? *[:=]' pyproject.toml server.json`.
   - Skip this step if the versions already equal `NEW` (first-release case).

4. **Verify the release is green.**
   - `uv sync && uv run pytest`
   - Do not continue if tests fail — report and stop.

5. **Commit the version bump.**
   - Stage only `pyproject.toml` and `server.json`.
   - Commit with a Conventional Commit message: `chore(release): vNEW`.
   - Skip if there is nothing to commit (first-release case).

6. **Tag the release commit.**
   - `git tag vNEW`

7. **Stop before pushing.** Report that the version-bump commit and tag `vNEW` are ready locally on `main`, and ask the user to run `git push origin main && git push origin vNEW` themselves. Do not run these pushes.

8. **Gather the changelog** since the previous tag (once the user confirms the push is done):
   - `git log <previous-tag>..HEAD --pretty=format:"%H %s"` — or `git log --pretty=format:"%H %s"` for the first release.
   - Resolve the repo slug with `gh repo view --json nameWithOwner -q .nameWithOwner`.
   - Since merges here are squashed, most subjects already carry a `(#123)` suffix — link that PR. Otherwise link the commit short SHA.
   - Build a markdown summary grouped by Conventional Commit type (Features, Fixes, Docs, Chores, …).

9. **Create the GitHub release** from the tag:
   ```
   gh release create vNEW --title "vNEW" --notes "$(cat <<'EOF'
   ## What's changed

   <grouped bullet list with PR/commit links>

   <one-paragraph description of the release>

   **Full changelog**: <previous-tag>...vNEW
   EOF
   )"
   ```
   - Omit the **Full changelog** line on the first release.

10. **Report** the new version, the tag, the release URL, and remind the user that the MCP registry entry (`server.json`) is published separately with `mcp-publisher` if they want the new version listed.
