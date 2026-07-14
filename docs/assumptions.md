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
| A-07 | Uploaded files are malware-scanned by a future deployment control; Phase 1 parser work uses local mocks only until that control exists. | Parsing hostile files is a security boundary. | Before real uploads |
| A-08 | Background jobs use a database-backed queue abstraction in Phase 4; no broker is selected in Phase 0. | Avoids premature middleware. | Phase 4 design |

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

- Phase 2: initial approved databases, logical names, schemas/tables/views, denied columns, read-only identities, row/byte/time limits, and representative mock data.
- Phase 3: Knowledge owner workflow, embedding/search choice, effective-date rules, and deletion/legal-hold requirements.
- Phase 4: Jira project/fields, recovery criteria ownership, scheduler/worker infrastructure, and job retention.
- Phase 5: Teams tenant/app registration, target channels, delivery policy, and approval contract.

## Unknown

- Production concurrency and latency SLOs
- Data volume and cross-source join sizes
- Corporate dependency allowlist and software composition analysis tooling
- Disaster recovery targets
- Whether Azure AI Search or pgvector is preferred in Phase 3
