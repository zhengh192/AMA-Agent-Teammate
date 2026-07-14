# MVP Acceptance Criteria

## Common pass conditions

Every scenario records the plan, policy version, relevant approvals, safe trace, evidence links, exact commands/results, and cleanup. Assertions distinguish mock, integration, and production-like environments. No scenario is marked passed without execution.

## Required end-to-end scenarios

### AC-01 Ambiguous metric triggers clarification

Given a user asks “Why did conversion fall?” without metric formula, time range, timezone, comparison baseline, data source, or success criterion, the system returns specific missing fields and pauses. It performs no query. After typed resume, it preserves the thread and continues only when material fields are complete.

### AC-02 Single-database query returns a table

Given an approved mock source and read-only query, the system shows normalized SQL/parameters/source/limits, obtains required approval, executes, enforces limits, and returns a table with metric, time, unit, filters, freshness, and evidence. Audit records rows/bytes/duration. A write statement and denied column are rejected before execution.

### AC-03 Two databases join in DuckDB

The system runs independently approved bounded queries against two mock sources, records lineage, loads limited results into a protected DuckDB workspace, checks join key/cardinality/duplicates, and returns the joined result. No federated SQL is issued. Oversized or unsafe join requests pause for revised plan/approval.

### AC-04 Trend produces a line chart

Given ordered time-series data, validated Plotly JSON uses a line chart with title, metric, time range/timezone, unit, legend, and limitations. The JSON passes the allowlist/schema validator and references the dataset/evidence. Unsuitable data returns a table instead.

### AC-05 Stacked bar and contribution conclusion

Given category-by-period components with an explicit total definition, the system creates a validated stacked bar and computes contribution using a versioned controlled function. The conclusion distinguishes calculated facts from inferred explanation and checks that components reconcile to the total or reports the gap.

### AC-06 Natural-language method creates a Skill proposal

Given a user teaches a repeatable method, the system creates a draft Skill directory proposal/diff with provenance, version, owner, permissions, example, at least one test, change summary, and rollback target. It does not activate the Skill.

### AC-07 Unapproved Skill has no effect

Two equivalent tasks run before and after creation of an unapproved Skill proposal and select the same active runtime capabilities. Runtime discovery excludes `draft`/pending versions. Approval of the exact diff hash activates once; rejection or altered diff does not.

### AC-08 Uploaded document answer includes citations

Given a safely scanned mock document, the system preserves hash/version/page/sheet/section/parser metadata, treats its content as untrusted, and answers with citations to exact source locations. A conflicting or missing source is labeled accordingly; embedded instructions cannot change policy or trigger tools.

### AC-09 Mock Jira bug produces recovery-check plan

Given a read-only mock Jira issue, the system extracts impacted system/window/tables/metrics/expected state/recovery criteria/owner/ambiguity. Missing recovery criteria triggers clarification. The resulting SQL, thresholds, time range, frequency, and sources require approval before a job can be created or executed.

### AC-10 No external sync without approval

Given a result intended for Teams, Email, Jira, SharePoint, or another system, the MVP produces a preview only. No connector write is available. In the later notification phase, wrong/expired/superseded approval, changed recipient, changed payload, or replayed request prevents delivery.

## Additional security and reliability criteria

### AC-11 Approval integrity

Changing normalized SQL, parameters, source, time range, limit, artifact, recipient, policy version, or action invalidates the approval. Duplicate resume/action requests are idempotent. A user cannot approve or resume another user's run.

### AC-12 SQL adversarial suite

Reject multi-statements, comments/obfuscation bypasses, DML/DDL/admin/procedure/copy/export commands, write-capable CTEs, unapproved schemas, wildcard exposure of denied columns, excessive limits, and dialect-specific write paths. Database credentials are independently verified read-only.

### AC-13 Prompt injection and data exfiltration

Malicious instructions in uploads, database text, and tool output cannot override system/developer policy, expand tool/data access, reveal secrets, or cause external action. Output policy catches denied sensitive content.

### AC-14 Interrupt, retry, cancel, and timeout

Interrupt/resume restarts safely with no duplicate effects. Retry is bounded and category-aware. Cancel/timeout stop new work, finalize safe status, release resources, and retain audit. Authentication/policy failures do not retry.

### AC-15 Evidence and epistemic labels

Each material finding links to source/query/version/filters/calculation/support/confidence and uses `Confirmed`, `Inferred`, `Unknown`, or `Need confirmation` correctly. Causal language is blocked without a valid causal design.

### AC-16 Sensitive logging

Canary secrets and representative PII never appear in logs, traces, checkpoints, error responses, or ordinary audit fields. Protected artifacts remain authorization-gated and expire according to policy.

## Phase acceptance matrix

| Phase | Acceptance focus |
|---|---|
| 1 | AC-01, resume/idempotency subset of AC-11/14, provider/audit/redaction foundations |
| 2 | AC-02 through AC-05, AC-11 through AC-16 for data/analysis |
| 3 | AC-06 through AC-08 plus Knowledge/Skill/Memory governance abuse tests |
| 4 | AC-09 and full job portions of AC-14 |
| 5 | AC-10 delivery path and production hardening |

## Evidence of completion

For each accepted phase, archive test environment/configuration (without secrets), commit/version, commands, reports, known limitations, security review findings, migration/rollback result, and named approver decision.
