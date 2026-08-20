---
description: Cut a new release — branch from main, merge develop, bump versions, tag, open a release PR, and publish a GitHub release
argument-hint: "[patch|minor|major]"
allowed-tools: Bash, Read, Edit
---

Cut a new release for stobot. The bump type is `$1` (default to `patch` if empty).

## Critical rules

- **Backend and frontend versions MUST always stay in sync** with each other and with the git tag. `backend/pyproject.toml` `version`, `ui/package.json` `version`, and the new tag must all reference the same version number.
- Git tags use a `v` prefix (e.g. `v0.5.1`); the version fields in the manifest files and the release branch name do NOT (e.g. `0.5.1`, `release/0.5.1`).
- Never push or publish until the version edits are committed.
- **A release is the one sanctioned case for branching off `main` and targeting `main` in a PR.** This overrides the usual "branch off `develop`" rule. The release branch is cut from `main`; `develop` is then merged into it; the PR targets `main`.

## Steps

1. **Sync `main` and cut the release branch.** (Do this FIRST, before any edits.)
   - `git fetch origin --tags`
   - **Determine the new version:**
     - Run `git tag --sort=-v:refname | head -5` to find the latest tag.
     - Parse the latest semver tag (strip the `v` prefix).
     - Bump according to `$1`:
       - `patch` (default) → `X.Y.(Z+1)`
       - `minor` → `X.(Y+1).0`
       - `major` → `(X+1).0.0`
     - Call the new version `NEW` (no `v`) and the tag `vNEW`.
   - Check out an up-to-date `main`: `git switch main && git pull --ff-only origin main`.
   - Create the release branch off `main`: `git switch -c release/NEW`.

2. **Merge `develop` into the release branch.**
   - `git merge origin/develop`
   - If there are conflicts, resolve them before continuing. Do not proceed with an unfinished merge.

3. **Update version manifests** to `NEW`:
   - Edit `version` in `backend/pyproject.toml` (`[project]` section).
   - Edit `version` in `ui/package.json`.
   - Confirm both now read exactly `NEW`.

4. **Commit the version bump.**
   - Stage only the two manifest files.
   - Commit with a Conventional Commit message: `chore(release): vNEW`.

5. **Tag the release commit.**
   - `git tag vNEW`

6. **Push all** (branch + tag).
   - `git push -u origin release/NEW`
   - `git push origin vNEW`

7. **Gather the changelog** since the previous tag (used for both the PR and the release):
   - `git log <previous-tag>..HEAD --pretty=format:"%H %s"` to list commits.
   - For each merge/PR, prefer linking the PR. Resolve the repo slug with `gh repo view --json nameWithOwner -q .nameWithOwner`.
   - Build a markdown summary grouped by type (Features, Fixes, Chores, etc.). Each entry links either the PR (`#123`) or the commit short SHA.

8. **Open the release PR into `main`:**
   ```
   gh pr create --base main --head release/NEW --title "chore(release): vNEW" --body "$(cat <<'EOF'
   ## What's changed

   <grouped bullet list with PR/commit links>

   <one-paragraph description of the release>

   **Full changelog**: <previous-tag>...vNEW
   EOF
   )"
   ```
   - **Merge this PR with a merge commit (not squash),** so the `vNEW` tag stays in `main`'s history.

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

10. **Report** the new version, the tag, the release branch, the PR URL, and the release URL.
