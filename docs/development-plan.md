# Development Plan

## Delivery rules

Each phase uses a dedicated branch or checkpoint commit, runs independently with mock/demo data, preserves earlier behavior, lists risks/postponed work, and has a documented rollback. At each phase end, report changes, exact verification results, risks, and the next approval; wait for human confirmation.

## Phase 0 — Architecture and repository rules

**Deliver:** product/system/LangGraph/security/data/governance/observability/license design, assumptions, acceptance criteria, repository instructions/tree, and safe environment template.

**Demo:** documentation walkthrough tracing an ambiguous analytics request through clarification, SQL approval, bounded execution, evidence, and final output.

**Verify:** required-file check, Markdown/link/diagram lint where available, secret scan, terminology/state consistency review, repository visibility/branch protection review.

**Done when:** all Phase 0 artifacts are reviewed; blockers have owners; repository remains private; no MIT license; product owner approves Phase 1.

**Rollback:** revert the Phase 0 checkpoint commit.

## Phase 1 — Chat foundation and Azure model integration

### Build order

1. Python/TypeScript workspaces, lockfiles, CI, lint/type/test baseline, dependency notices.
2. Domain IDs/configuration, metadata repositories, migrations, artifact interface, audit events.
3. `LLMProvider`, `AzureOpenAIProvider`, `MockLLMProvider`, per-role profiles, capability/startup checks.
4. Minimal typed LangGraph: input guard, goal extraction, deterministic completeness, clarification interrupt/resume, direct response, output guard.
5. FastAPI session/run/stream/approval contracts.
6. React chat/session/status/plan/evidence shell with mock paths.
7. Identity development adapter, authorization hooks, redaction, quotas, telemetry.
8. Integration/e2e tests and a mock-provider demo.

**Demo:** ambiguous request pauses for clarification, resumes with the same thread, streams status, and returns a structured answer through a mock or approved Azure deployment.

**Done when:** fresh local setup is documented and repeatable; no secret is committed; provider SDK stays behind adapter; mock tests are deterministic; checkpoint resume and duplicate-resume behavior pass; real Azure smoke test is separately identified if credentials are available.

**Risks:** Azure capability/version variance, identity unknown, checkpoint/schema coupling, sensitive prompt logs.

**Postponed:** real databases, charts, Knowledge activation, arbitrary Python, jobs, Teams.

**Rollback:** disable Azure profile/use mock; revert Phase 1 migrations and commit with documented data compatibility.

## Phase 2 — Database, analysis, and charts

1. Connector registry and mock PostgreSQL/MySQL/SQL Server dialect fixtures.
2. Catalog/policy and SQLGlot AST safety gateway with adversarial tests.
3. Approval-bound SQL preview and read-only execution limits/audit.
4. Dataset quality metadata and ephemeral artifact lifecycle.
5. Bounded DuckDB cross-source joins with cardinality/size guards.
6. Controlled analysis function library; dataframe decision spike.
7. Plotly JSON allowlist/schema/content validation and table fallback.
8. End-to-end single/cross-source analysis tests with mock data.

**Done when:** required Phase 2 acceptance cases pass against mocks and approved integration sources; write/bypass tests fail safely; evidence reproduces calculations; temporary artifacts are cleaned.

**Risks:** dialect bypass, excessive scans/egress, sensitive joins, misleading statistics/charts.

**Postponed:** arbitrary generated Python unless sandbox is independently approved; Knowledge; Jira/jobs.

## Phase 3 — Knowledge, Skill, and Memory

1. Safe upload/quarantine/parser contracts and mock scanning.
2. Document/version/chunk provenance and protected artifact storage.
3. Search backend decision spike (pgvector vs Azure AI Search), retrieval authorization, citations.
4. Proposal/diff/approval/activation for Knowledge, Skills, and Memory.
5. Git-backed Skill structure, tests, version/deprecation/rollback.
6. Memory scopes, expiry/correction/deletion, context assembly.
7. Injection, conflict, stale source, unauthorized retrieval, and non-activation tests.

**Done when:** citations resolve to exact source locations; unapproved proposals never affect behavior; rollback/deletion and access boundaries pass.

## Phase 4 — Data quality, Jira, and background jobs

1. Bounded Jira read/search connector plus approval-gated issue creation and status transition.
2. Deterministic recovery-context completeness and clarification.
3. Data-quality check definitions and pre/post-incident evidence.
4. Asynchronous job state machine, worker lease, retry, checkpoint, cancellation, timeout, history.
5. Exact-plan approval before job creation/execution.
6. Operational dashboards, alerts, and failure/recovery tests.

**Done when:** Jira reads/searches are bounded; create/transition writes require exact persisted approval and are auditable; a mock issue yields an owner-confirmed recovery plan; background jobs are bounded, resumable, cancellable, and cannot perform unapproved external writes.

## Phase 5 — Teams notification and production hardening

1. Confirm channel approach: direct Teams Bot/Graph or gateway limited to notification delivery.
2. Implement `NotificationChannel` and exact recipient/content/artifact approval contract.
3. Identity/SSO/RBAC integration, managed secrets, network/egress, managed stores.
4. Load/resilience/security/privacy/license reviews, backup/restore, SLOs/runbooks.
5. Controlled pilot and rollback exercise.

**Done when:** delivery cannot occur without current exact-payload approval; production controls and owners sign off; incident/rollback paths are exercised.

## Cross-phase quality gates

- Unit, contract, integration, security abuse, and end-to-end tests proportional to the phase
- Ruff, type checker, pytest; frontend lint, Vitest, build, and Playwright when present
- Lockfile/SBOM/license/vulnerability/secret scanning
- Migration forward/rollback rehearsal
- Evidence and audit contract validation
- Threat model and assumptions updated with every boundary change
