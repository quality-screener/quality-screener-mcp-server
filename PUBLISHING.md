# Publishing & directory listings

How to get the Quality Screener MCP server listed everywhere people discover MCP
servers. Do the steps **in order** — the official registry is the anchor that the
other directories pull from.

> Canonical facts (reuse verbatim everywhere):
>
> | Field | Value |
> | --- | --- |
> | Registry name / namespace | `io.github.quality-screener/qscreener` |
> | Display name | Quality Screener |
> | Remote endpoint | `https://mcp.qualityscreener.io/mcp` (transport: `streamable-http`) |
> | Repository | `https://github.com/quality-screener/quality-screener-mcp-server` |
> | Website | `https://qualityscreener.io` |
> | Documentation URL | `https://github.com/quality-screener/quality-screener-mcp-server` |
> | Privacy policy URL | `https://github.com/quality-screener/quality-screener-mcp-server/blob/main/PRIVACY.md` |
> | Support contact | `info@qualityscreener.io` |
> | Auth | OAuth 2.0 (browser sign-in), or `X-Stobot-CLI-Token` header |
> | Categories/tags | finance, stocks, investing, screener, equities, fundamentals |
> | Short description (≤100 chars) | `Screen and score stocks with the Quality Screener engine: filters, custom scores, and history.` |

---

## Already done in this repo

- ✅ **`server.json`** finalized with the real namespace and schema-validated against
  `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`.
- ✅ **Tool annotations** added to every tool in `qscreener_mcp/server.py`
  (`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint` + titles) —
  required for the Anthropic directory, useful everywhere else.
- ✅ **Privacy policy** published as [`PRIVACY.md`](PRIVACY.md) and summarized in
  the README. Required by the Anthropic directory — a missing or incomplete
  policy is an immediate rejection.
- ✅ **Support contact** (`info@qualityscreener.io`) and **documentation URL**
  (this repo) documented in the README's Support section.

> **Note:** `server.json` has no field for a privacy policy or support contact —
> the schema only carries `description`, `websiteUrl`, `repository`, and `icons`.
> Those two values are entered in the Anthropic submission portal (Listing step);
> do not try to add them to `server.json` or publishing will fail validation.

---

## Step 1 — Official MCP Registry (the anchor)

**Who must run this:** a person who is a **member of the `quality-screener` GitHub
org**. The `mcp-publisher` CLI authenticates the logged-in GitHub *user*, and the
registry only allows publishing to `io.github.quality-screener/*` if that user
belongs to the org. Nobody without org membership can do this step — it cannot be
automated from CI without an org-scoped token.

Run all commands **from the repo root** (the directory containing `server.json`):

```bash
# 1. Install the mcp-publisher CLI (macOS/Linux; also on Homebrew: `brew install mcp-publisher`)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/

# 2. Log in via GitHub (opens a device-code flow in the browser; approve as a
#    member of the quality-screener org)
mcp-publisher login github

# 3. Publish server.json to the registry
mcp-publisher publish
```

Expected final output:

```
✓ Successfully published
✓ Server io.github.quality-screener/qscreener version 0.1.0
```

**Verify** the listing is live:

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.quality-screener/qscreener"
```

You should see the server's metadata in the JSON results.

> **Re-publishing later:** bump `"version"` in `server.json` (it must match
> `version` in `pyproject.toml`) and re-run `mcp-publisher publish`. Republishing
> the same version is rejected.

> **Troubleshooting**
> - *"You do not have permission to publish this server"* → the logged-in GitHub
>   user is not a member of the `quality-screener` org. Log in as an org member.
> - *"Invalid or expired Registry JWT token"* → re-run `mcp-publisher login github`.

---

## Step 2 — Quick directories

All three want the same handful of facts (see the table at the top). Ready-to-paste
copy below.

### mcp.so — web form at https://mcp.so/submit

| Field | Value |
| --- | --- |
| Name | Quality Screener |
| GitHub / URL | `https://github.com/quality-screener/quality-screener-mcp-server` |
| Server URL | `https://mcp.qualityscreener.io/mcp` |
| Category | Finance |
| Description | Screen and score stocks with the Quality Screener engine. Filter the scored universe, compute custom quality scores from weighted financial metrics, inspect score history, manage saved scoring systems, and generate shareable screen links — as the signed-in user, over the same data as the web dashboard. |

### PulseMCP — submit at https://www.pulsemcp.com/submit

| Field | Value |
| --- | --- |
| Name | Quality Screener |
| Source code URL | `https://github.com/quality-screener/quality-screener-mcp-server` |
| Remote URL | `https://mcp.qualityscreener.io/mcp` |
| Tags | finance, stocks, investing, screener, fundamentals |
| Short description | Screen and score stocks with the Quality Screener engine: filters, custom scores, and history. |
| Long description | A hosted MCP server for the Quality Screener stock-screening engine. Agents can screen and filter the scored universe, compute custom quality scores, inspect per-ticker score history, manage saved scoring systems, and generate shareable screen links. Multi-tenant and credential-free: each request carries the caller's own token, so a single deployment serves many users. Connect over OAuth (browser sign-in) or a per-request token header. |

### PR-based directory (mcpservers.org / awesome-mcp-servers)

The `mcpservers` GitHub org exposes no public PR repo, so the dominant PR-based
directory to target is **`punkpeye/awesome-mcp-servers`** (also confirm whether the
maintainers of mcpservers.org accept the same entry — check their site footer /
CONTRIBUTING before opening the PR).

**Entry line** (add under the **Finance & Fintech** section, alphabetically):

```markdown
- [quality-screener/quality-screener-mcp-server](https://github.com/quality-screener/quality-screener-mcp-server) 🎖️ 🐍 ☁️ 🏠 🍎 🪟 🐧 - Screen and score stocks with the Quality Screener engine: filter the scored universe, compute custom quality scores, inspect score history, and share screen links.
```

Legend used: 🎖️ official implementation · 🐍 Python · ☁️ cloud service · 🏠 local
service · 🍎🪟🐧 macOS/Windows/Linux.

**PR title:** `Add Quality Screener (stock screener) to Finance & Fintech`

**PR body:**

> Adds the Quality Screener MCP server — a hosted MCP façade over the Quality
> Screener stock-screening API. Tools let an agent screen/filter the scored
> universe, compute custom quality scores, inspect score history, manage saved
> scoring systems, and generate shareable screen links.
>
> - Repo: https://github.com/quality-screener/quality-screener-mcp-server
> - Remote endpoint: https://mcp.qualityscreener.io/mcp (streamable-http, OAuth)
> - Also published to the official MCP Registry as `io.github.quality-screener/qscreener`.

---

## Step 3 — Anthropic Connectors Directory

Submission happens in the **Claude.ai admin-settings portal**, not a public intake
form: <https://claude.ai/admin-settings/directory/submissions/new>

> ⛔ **Hard prerequisite: a Team or Enterprise organization.** Admin settings do
> not exist on individual plans, so the portal is unreachable from a personal
> account. By default only org Owners / Primary owners can submit; on Enterprise
> an Owner can delegate via a custom role with the **Directory management**
> permission. Nothing else in this step matters until this is resolved.

Reference docs: [submission](https://claude.com/docs/connectors/building/submission)
· [review criteria](https://claude.com/docs/connectors/building/review-criteria)
· [authentication](https://claude.com/docs/connectors/building/authentication)

### Readiness

- ✅ **Tool annotations** — every tool has a `title` plus `readOnlyHint` or
  `destructiveHint` (see `qscreener_mcp/server.py`).
- ✅ **Read/write separation** — no catch-all `api_request`-style tool, which is
  an automatic rejection.
- ✅ **Tool names** — all well under the 64-character limit.
- ✅ **OAuth discovery** — the live server returns `401` with a
  `WWW-Authenticate: Bearer … resource_metadata=…` header, advertises a
  `registration_endpoint` (DCR) and `code_challenge_methods_supported: ["S256"]`.
- ✅ **Privacy policy** — [`PRIVACY.md`](PRIVACY.md).
- ✅ **Support contact** — `info@qualityscreener.io`.
- ✅ **Documentation URL** — this repository.
- ⚠️ **Icon** — supply a square PNG/SVG of the Quality Screener logo.
- ⛔ **Test account** — a *fully populated* account plus step-by-step reviewer
  access instructions is required.

### Portal field values

  | Portal field | Value |
  | --- | --- |
  | Server name (≤100 chars) | Quality Screener |
  | MCP server URL | `https://mcp.qualityscreener.io/mcp` |
  | Transport | streamable HTTP |
  | Tagline (≤55 chars) | `Screen and score stocks on quality fundamentals` |
  | Description (≤2000 chars) | Screen and score stocks with the Quality Screener engine: filter the scored universe, compute custom quality scores, inspect score history, manage saved scoring systems, and share screen links. Read and analysis only — it executes no trades and moves no funds. |
  | Documentation URL | `https://github.com/quality-screener/quality-screener-mcp-server` |
  | Privacy policy URL | `https://github.com/quality-screener/quality-screener-mcp-server/blob/main/PRIVACY.md` |
  | Support contact | `info@qualityscreener.io` |
  | Auth type | `oauth_dcr` today — see the note below |

> **State the no-trading fact explicitly.** The directory rejects connectors that
> transfer money, cryptocurrency, or other financial assets. This server only
> reads and analyses, but say so in the description so a reviewer does not have
> to infer it.

---

## Known technical gaps (fix before directory traffic)

These do not block *submission*, but they will break real users once the
connector is listed.

| Gap | Where | Impact |
| --- | --- | --- |
| OAuth client registrations are written to `~/.config/qscreener/mcp_clients.json` | `qscreener_mcp/oauth.py` | Railway's filesystem is ephemeral — every redeploy wipes registrations, so connected users' `client_id`s become unknown and they must reconnect. Needs a real store. |
| `_pending` / `_codes` are in-memory dicts | `qscreener_mcp/oauth.py` | The auth handshake breaks outright with more than one replica. |
| Metadata advertises `refresh_token` but `exchange_refresh_token` raises `unsupported_grant_type`, and no refresh token is ever issued | `qscreener_mcp/oauth.py` | Claude refreshes reactively on `401`. With no refresh path, a revoked token is a dead end rather than a silent renewal. Either implement refresh with rotation (required for public clients) or stop advertising the grant. |
| DCR at directory scale | — | Anthropic recommends CIMD or Anthropic-held credentials over DCR, because DCR registers a **new client on every fresh connection**. Email `mcp-review@anthropic.com` to set up `oauth_anthropic_creds`, which also resolves the two rows above. |
| Protected-resource `resource` is `https://mcp.qualityscreener.io/` but users enter `https://mcp.qualityscreener.io/mcp` | — | Docs require an exact match *including the path*. It works with Claude Code today, so verify rather than assume — but it is a cheap fix. |

---

## Blockers that still need a human

| Blocker | Blocks | Notes |
| --- | --- | --- |
| Team or Enterprise Claude organization | Step 3 entirely | The submission portal lives in admin settings; unreachable on an individual plan |
| Run `mcp-publisher` as a `quality-screener` org member | Step 1 (and the directories that pull from it) | 3 commands above; cannot be automated without an org-scoped token |
| Fully populated test account + reviewer instructions | Step 3 | Required; must let a reviewer exercise every tool end to end |
| Logo file | Step 3 (degrades, doesn't block) | Square PNG/SVG |
