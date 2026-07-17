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
