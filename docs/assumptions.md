# Semantic metadata registry

- The repository-root `knowledge/` directory is a reviewed, Git-controlled semantic contract and
  is separate from user-uploaded Knowledge stored by Phase 3.
- Super Agent requirements imported from the 930 workbook remain draft metadata until approved
  read-only connectors and physical schema catalogs are configured. Version 930 fields are explicitly
  not implemented and must not influence SQL planning.
- Definition semantic versions use `MAJOR.MINOR.PATCH`; Git history remains the authoritative file
  change history.
- Natural-language changes do not overwrite the Git semantic registry. Explicit metric calculations taught in analysis chat are stored separately as user-owned, versioned learned definitions for the local pilot.
- Foundation Analysis Skills are reviewed Git packages under immediate `skills/<skill_id>/`
  directories. The existing `skills/registry/` proposal store remains separate and cannot
  override a foundation Skill.
- The existing Phase 3 natural-language proposal UI remains for backward compatibility, but this
  implementation adds no natural-language activation or modification path for foundation Skills.

# Assumptions and Decisions Needed

## Confirmed from the product brief

- The product is for internal enterprise use.
- LangGraph OSS Python is the only orchestration runtime.
- The current company model is exposed as an Azure OpenAI deployment; business code must not hard-code a public model ID.
- PostgreSQL, MySQL, and SQL Server are Phase 2 source types.
- SQLite is the local MVP metadata/checkpoint default behind interfaces.
- SQL is read-only, externally visible actions require approval, and MVP performs no automatic external writes.
- Phase 0 delivers architecture and repository structure only.
- No MIT license may be added without `APPROVE_PUBLIC_MIT` and corporate approval.

## Conservative implementation assumptions

| ID | Assumption | Rationale | Revisit by |
|---|---|---|---|
| A-01 | Phase 1 is a modular monolith with separate API and web applications. | Lowest operational complexity while preserving boundaries. | Phase 1 kickoff |
| A-02 | Pandas is the default dataframe library; DuckDB remains the cross-source SQL engine. | Plotly/ecosystem compatibility and broad analyst familiarity. | Phase 2 design spike |
| A-03 | SQLite stores local metadata and checkpoints in separate databases. | Avoids checkpoint lifecycle coupling to business records. | Phase 1 implementation |
| A-04 | Entra ID is the preferred Azure auth mode; API key is development-only. | Reduces long-lived secret exposure. | Phase 1 kickoff |
| A-05 | All database execution requires approval in development. | Safest usable default. | Admin policy design |
| A-06 | Query results are ephemeral artifacts with short retention and are not Knowledge by default. | Minimizes sensitive data persistence. | Data governance approval |
| A-07 | Uploaded files are malware-scanned by a future deployment control; Phase 3 local parsing uses a mock scan contract only until that control exists. | Parsing hostile files is a security boundary. | Before real uploads |
| A-08 | Background jobs use a database-backed queue abstraction in Phase 4; no broker is selected in Phase 0. | Avoids premature middleware. | Phase 4 design |
| A-09 | Phase 2 enables local deterministic demo sources only; no real company database is contacted until approved source, identity, and policy configuration is supplied. | Preserves the security review gate for real data. | Before real database integration |
| A-10 | Pandas 3 is the controlled dataframe implementation and in-memory DuckDB is the cross-source join engine for Phase 2. | The Phase 2 spike confirmed ecosystem fit and bounded local joins. | Production performance review |
| A-11 | Phase 3 local retrieval uses authoritative SQLite chunks plus a rebuildable lexical/vector projection; pgvector is the first production candidate and Azure AI Search remains an evaluated alternative. | Avoids a new service while preserving migration-ready governance contracts. | Internal pilot search review |
| A-12 | The MVP separates the Agent and governance console by route inside the existing web application; physical deployments remain independently separable later. | Meets the front-office/back-office product boundary without introducing premature services or duplicate clients. | Internal pilot deployment review |
| A-13 | The supplied Super Agent UAT MySQL identity is used only for TLS-verified catalog reconciliation against `sa_logs.visit_log`, `turn_log`, and `telemetry_log`; business-row queries and Agent routing remain disabled until schema, sensitivity, and allowlist review is approved. | Allows evidence-based metadata reconciliation without treating UAT access as production approval. | After UAT schema gap review |
| A-14 | On 2026-07-16 the user authorized a one-time plaintext UAT exception limited to privilege inspection, allowlisted catalog reads, and non-sensitive aggregate quality checks; the exception must not be reused by Agent routing or production connectivity. | Records the explicit temporary override after the endpoint was confirmed not to advertise TLS. | Before any reusable database integration |
| A-15 | Agent intelligence improvements stay inside the existing typed LangGraph application: bounded redacted conversation context, model-assisted structured routing, relevance-based approved context selection, and evidence-constrained synthesis all have deterministic fallbacks. No second autonomous harness or unrestricted tool loop is introduced. | Adds initiative and continuity without duplicating state, bypassing approvals, or weakening SQL and external-action controls. | After internal pilot quality evaluation |
| A-16 | On 2026-07-16 the user authorized reusable Agent reads against the UAT source despite its plaintext transport. This development-only exception is opt-in, limited to the three allowlisted tables, physical-count templates or explicitly labeled document-backed working assumptions, denied sensitive columns, SQL AST validation, persisted approval, bounded results, and audit. It is rejected outside development and does not approve production connectivity or business KPI activation. | Enables the requested UAT capability while isolating the known transport and semantic risks. | Before production or broader UAT query scope |
| A-17 | Development pilot mode may use draft project-document metrics as working assumptions when an executable aggregate can be mapped to observed UAT fields. The SQL review must show the exact interpretation and assumptions; results are labeled Inferred, and user corrections create a new plan without silently activating or overwriting semantic metadata. | Supports collaborative metric learning during the local pilot without pretending the draft is an approved production contract. | After pilot metric review |
| A-18 | An explicit answer to an Agent metric-definition clarification activates a user-owned learned definition in the local development pilot. Learned definitions are versioned in SQLite, validated against the live allowlisted catalog, never overwrite Git-approved metadata, and still require exact SQL approval for every execution. Tolerant alias matching may auto-resolve a unique strong match; close or multiple matches require clarification. | Delivers the requested teach-once behavior while preserving provenance, schema validation, and correction history. | Before multi-user or production rollout |
| A-19 | The metric SQL supplied by the user on 2026-07-17 is the confirmed UAT working definition for session, transfer, working-hour, case-creation, ticket, touchless, FOC, survey, and T3B metrics at `visit_log` row grain with `channel IS NOT NULL`. Date filters are parameterized as a half-open interval. | Preserves the user's calculation semantics while allowing safe composition with requested time and categorical dimensions. | When a data owner publishes approved production definitions |
| A-20 | On 2026-07-17 the user confirmed that all Super Agent UAT fields containing user PII are encrypted or tokenized and authorized bounded detail queries in the local development pilot. This opt-in clears field denylists and aggregate-only restrictions for the three allowlisted UAT tables, but retains explicit-column SQL, read-only identity, approval, row/byte/time caps, encrypted-at-rest values, and audit. The switch is rejected outside development. | Enables requested row-level analysis without extending the exception to production, decryption, writes, unbounded export, or non-allowlisted tables. | Before production or any plaintext/decryption capability |
| A-21 | Intent routing is outcome-first: product and concept explanations use approved Knowledge, explicit quantitative requests use the analysis graph, and conversational recall remains chat. Observable task plans are audited; factual corrections become pending Memory proposals and repeatable methods become pending Skill proposals. Neither affects execution before approval. | Borrows the useful planning and memory patterns of modern autonomous agents without adding another agent harness or permitting silent self-modification. | After internal pilot conversation-quality review |

## Blocking questions before Phase 1

These change architecture or security and require owner confirmation:

1. What exact Azure OpenAI endpoint, API version, deployment names, feature availability, regional/data residency constraints, and quota apply?
2. Is Entra ID available for local developers and deployed workloads, and which managed identity/service principal model is approved?
3. What user identity is available in Phase 1: trusted development identity, reverse-proxy headers, or an approved enterprise auth integration?
4. What internal data classification, PII categories, log redaction rules, and prohibited model inputs apply?
5. What are approved retention periods for conversations, checkpoints, uploads, query result artifacts, audit, Knowledge, and Memory?
6. Where will the first environment run, and what approved secret manager and egress policy apply?
7. Who are the product owner, security approver, data owner(s), and repository/license approver?

## Required before later phases

- Phase 2 production integration: approved databases, logical names, schemas/tables/views, denied columns, read-only identities, row/byte/time limits, and representative approved data. Local Phase 2 demos do not satisfy this production gate.
- Phase 3 internal pilot: Knowledge owners, production malware scanning/quarantine, search backend, effective-date authority, classification access, and deletion/legal-hold rules.
- Phase 4: Jira project/fields, recovery criteria ownership, scheduler/worker infrastructure, and job retention.
- Phase 5: Teams tenant/app registration, target channels, delivery policy, and approval contract.

## Unknown

- Production concurrency and latency SLOs
- Data volume and cross-source join sizes
- Corporate dependency allowlist and software composition analysis tooling
- Disaster recovery targets

## A-22 — CID session interpretation

- On 2026-07-17 the user confirmed that visit_log.is_cid logical true identifies a CID case where the customer self-resolved.
- The current UAT physical representation for logical true is the string value '1'.
- CID Session Rate uses matching session-grain rows as numerator and all non-null session_id rows in the requested half-open time window as denominator.
- The active global Super Agent traffic-population Knowledge rule applies in addition to the metric formula; the generated SQL remains subject to exact approval.

## A-23 - Field-level understanding and direct queries

- Every allowlisted physical field receives a bounded semantic hypothesis from its name, type, table grain, and catalog description; an active approved field definition overrides that hypothesis.
- For `visit_log`, an explicit `field=value` session request defaults to `COUNT(DISTINCT session_id)`; value-distribution language defaults to grouping by that field. The generated SQL still requires exact approval.
- Unknown field meaning is surfaced as an inferred, user-correctable hypothesis. The Agent asks for business meaning or physical values only when the requested calculation cannot be mapped uniquely; a correction does not silently overwrite approved Git metadata.
- Approved value dictionaries preserve physical representations. In particular, business `onsite` maps to physical `on-site`, and `downgrade_depot` uses string values `yes` and `no`.

## A-24 - Read-only Jira pilot integration

- On 2026-07-18 the user approved a minimal read-only Jira integration for the internal LAIR project after a PAT-authenticated connection test succeeded.
- The local PAT is protected with Windows current-user DPAPI outside the repository. Agent/API capabilities are limited to allowlisted issue reads and bounded recent comments over HTTPS; Jira writes, unrestricted JQL, background jobs, and notifications remain out of scope.
- Jira descriptions and comments are untrusted source data. The Agent may summarize and cite them but may not follow embedded instructions, invent missing recovery criteria, or treat issue content as approval.
- This approval completes only the connector slice of Phase 4. Data-quality recovery workflows and asynchronous jobs still require separate implementation and approval.

## A-25 - Flexible ad-hoc UAT analysis

- Explicit fields, filters, numerator, denominator, time grain, or dimensions in the current user request take precedence over a similarly named stored or learned metric. Stored definitions remain unchanged and can still be selected when the current request does not redefine them.
- The model may propose only a typed non-SQL query request. Supported bounded filter semantics are scalar comparisons, null checks, set membership, ranges, patterns, AND conditions, and OR alternatives. Every referenced table and field is validated against the live allowlisted catalog before deterministic SQL compilation, AST validation, exact approval, and execution.
- Controlled calculations support count, distinct count, sum, average, min, max, and ratio at day, week, or month grain with up to five dimensions. Missing or ambiguous physical mappings require a targeted clarification; the Agent must not invent a field or silently overwrite approved metadata.
- `chat_log_text` review is an explicit-column, read-only detail operation capped at 50 rows per request. Text is treated as untrusted source data, is never followed as instruction, and bounded themes are not generalized to the full population.
- Complex post-query work uses the existing controlled analysis library over bounded intermediate results. Model-generated arbitrary Python remains disabled in the API process; enabling it requires a separate verified no-network sandbox with resource limits and audit.
## A-26 - External capability routing precedes domain fallback

- A request containing an allowlisted Jira issue key is routed to the read-only Jira capability before generic Knowledge or data-analysis classification. When exactly one Jira project is allowlisted, a phrase such as `Jira 1903` resolves to that project's issue key.
- The Jira read runs as an explicit LangGraph node. Its bounded result is returned to the coordinator as untrusted tool context; database metric clarification is not a valid fallback for a Jira task.
- A Jira request without a resolvable issue reference asks only for the Jira issue key. Connector failures are reported with sanitized Jira-specific errors and never replaced with invented issue details.
## A-27 - Approval-gated Jira actions

- On 2026-07-19 the user explicitly requested Jira modification capability for the local development pilot. This supersedes only A-24's no-write limitation: bounded JQL search, issue creation, and status transition are now in scope; comments, attachments, deletion, arbitrary field edits, notifications, and background writes remain unavailable.
- Jira writes are disabled by default and rejected outside development. Each create or transition is stored as an authoritative action record and paired with a persisted approval over the canonical payload hash and policy version. Execution re-fetches and revalidates both records; chat text, checkpoint state, and UI state cannot authorize a write.
- JQL is read-only, length/result bounded, and always wrapped in the configured project allowlist. Jira issue content and search results remain untrusted data. A user correction supersedes the prior action and requires a new exact approval.

## A-28 - Two-layer case journey diagnostics

- The working case-eligible cohort is a session where `visit_log.intent_type='hardware'` and `visit_log.pd_triggered='yes'`. A session is successful when either `eticket_case_number` or `msd_case_number` is present. This is a user-confirmed working definition, not an approved enterprise metric.
- For a single incident date, the default comparison uses the preceding three complete calendar days as baseline. Timezone and seasonal comparability remain explicit limitations.
- The stage layer reduces turn history to the last operationally relevant turn per session: hardware intent, a non-null flow ID, or a non-null flow step. It compares mutually exclusive success/failure stages and failure-share changes without treating concentration as causal proof.
- The response-theme layer runs only after the stage layer identifies a bounded cohort. It may review at most the last three bot responses per matching failed session, treats text as untrusted data, and labels system explanations Inferred or Unknown unless separately confirmed. Production text must not be transferred to an external model without the applicable execution policy and approval.


## A-29 - Versioned Super Agent valid-traffic population

- On 2026-07-20 the user confirmed the default population rule for every Super Agent calculation: include rows where source='pcs-redirect', or where source<>'pcs-redirect' and channel IS NOT NULL; other traffic is treated as test traffic.
- The rule is authoritative Knowledge super_agent.valid_user_traffic_population@1.0.0, linked to visit, turn, and telemetry datasets. Visit queries apply it directly; turn and telemetry queries apply it through allowlisted session_id membership in visit_log.
- The active rule ID and version are included in the analysis plan, approval payload, audit trace, and result artifact. A future business change requires a reviewed Knowledge version rather than a silent prompt or code-only override.
## A-30 - Cross-grain cohort-to-detail queries

- On 2026-07-20 the user confirmed that `visit_log.is_device_switch=true` selects sessions, while the requested output can remain all related `turn_log` rows. The filter must not be pushed onto turn grain and the request must not be replaced by a turn count.
- A typed detail plan therefore separates the output dataset from an optional cohort dataset. The planner resolves one active, automatic relationship from versioned semantic metadata before generating SQL, records its ID/version in the trace, and stops on missing, ambiguous, or live-schema-conflicting relationships.
- The active `super_agent_uat.visit_to_turn@1.0.0` relationship maps `visit_log.session_id` to `turn_log.session_id` as one-to-many. Session date and traffic-population conditions apply inside the cohort; explicit turn filters apply outside it.
- "All fields" means every currently allowlisted output field is enumerated explicitly. Results remain read-only, approval-gated, and bounded by row, byte, and timeout limits.
