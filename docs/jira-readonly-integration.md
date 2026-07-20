# Bounded Jira integration

## Scope

This Phase 4 pilot lets the Agent read an explicitly referenced Jira issue, run allowlist-bounded JQL searches, create an issue, or transition an issue status. It preserves the existing LangGraph application and does not add a second agent runtime.

The connector exposes:

- `GET /api/integrations/jira/health`
- `GET /api/integrations/jira/issues/{issue_key}`
- automatic issue lookup and bounded JQL search from chat
- approval-gated issue creation and status transition from chat

Searches are read-only and do not require approval. Every create or transition first displays the exact payload in the chat UI and requires a persisted approval tied to its hash. Comments, attachments, deletion, arbitrary field editing, unrestricted cross-project JQL, background jobs, and notifications are not implemented.

## Local credential setup

The local pilot uses a Jira personal access token protected by Windows current-user DPAPI. The plaintext token must not be put in `.env`, source files, SQLite, logs, screenshots, or chat.

The default encrypted token path is:

```text
%LOCALAPPDATA%\AMA-Agent-Teammate\secrets\jira_pat.dpapi
```

Create or replace it from a trusted local PowerShell prompt without echoing the token:

```powershell
$secret = Read-Host "Jira PAT" -AsSecureString
$directory = Join-Path $env:LOCALAPPDATA "AMA-Agent-Teammate\secrets"
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$secret | ConvertFrom-SecureString | Set-Content (Join-Path $directory "jira_pat.dpapi")
```

Then enable the ignored local `.env` configuration:

```text
AMA_JIRA_ENABLED=true
# Development-only opt-in; leave false for read/search-only operation.
AMA_JIRA_WRITE_ENABLED=false
AMA_JIRA_SEARCH_MAX_RESULTS=50
AMA_JIRA_BASE_URL=https://jira.xpaas.lenovo.com
AMA_JIRA_ALLOWED_PROJECTS=LAIR
```

The DPAPI value is bound to the Windows user that created it. A service deployment must replace this token provider with an approved enterprise secret manager and workload identity boundary.

## Trust and audit behavior

- The project allowlist is enforced before issue access and is server-side added to every JQL search.
- The transport uses HTTPS, disables environment proxies for the internal endpoint, applies a timeout, and caps response bytes.
- Reads and searches return only bounded core issue fields and recent comments. Search results are capped at 50.
- Issue descriptions, comments, and search results are untrusted source data. Instructions embedded in them never become system instructions or approvals.
- Writes are disabled by default and rejected outside development. Enabling them does not bypass per-action approval.
- Create/transition payloads are persisted separately from LangGraph checkpoints. Approval and execution revalidate action ID, approval ID, payload hash, decision, and policy version.
- Audit uses safe IDs, hashes, issue keys, decisions, and result codes. Tokens, Authorization headers, raw descriptions, and raw error bodies are excluded.
- Missing issue facts, target status, creation details, or recovery criteria remain Unknown and must be clarified.

## Verification

Run:

```text
uv run ruff check .
uv run mypy apps/api/src
uv run pytest
```

With local Jira enabled, verify the sanitized endpoints:

```text
GET /api/integrations/jira/health
GET /api/integrations/jira/issues/LAIR-1514
```

Do not paste the health request headers or local DPAPI file contents into bug reports.
