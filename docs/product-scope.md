# Product Scope

## Product outcome

AMA Data Analysis Teammate is an internal digital colleague that turns natural-language requests into governed, evidence-linked analytical work. It clarifies ambiguous requests, reads approved business material, queries authorized data sources, performs bounded analysis, creates validated tables/charts, and proposes reusable Knowledge, Skills, and Memory.

## Primary users

- Business analysts and product/operations owners who need explainable analysis
- Data engineers and reliability owners who need repeatable data checks
- Administrators who configure data access, retention, and trusted execution modes
- Reviewers who approve SQL, scheduled work, reusable knowledge, and external delivery

## Core user journeys

1. Ask an analytical question, clarify metric/time/source/success criteria, approve a plan, and receive evidence-linked findings.
2. Query one or more databases through read-only connectors, joining only bounded results locally in DuckDB.
3. Upload a document, preserve provenance/version metadata, retrieve facts with citations, and propose governed Knowledge/Skill/Memory changes.
4. Inspect an analysis plan, SQL preview, execution status, chart/table, evidence, and error summary.
5. In Phase 4, interpret a read-only Jira issue and propose an approval-gated recovery check.

## MVP capabilities

- Single conversational interface with sessions, uploads, streaming status, plan, approval controls, results, evidence, and trace summary
- Coordinator, Data Analyst, and Knowledge Curator as logical roles inside one graph application
- Azure OpenAI provider abstraction supporting per-role deployment profiles, structured output, tools, streaming, timeout/retry, and token accounting
- PostgreSQL, MySQL, and SQL Server connector registry with enforced policies
- SQL AST validation, query constraints, audit, and default pre-execution approval
- Controlled analytical operations plus validated Plotly JSON
- Versioned, approval-controlled Knowledge, Skills, and Memory
- Local SQLite metadata/checkpoint implementations behind migration-ready interfaces

## Non-goals for the first release

- Dynamic multi-agent swarm or unrestricted autonomous action
- Dependencies on Anton, Hermes, OpenClaw, AutoGen, CrewAI, or another complete agent harness
- Automatic writes to Jira, databases, Teams, SharePoint, or other external systems
- Arbitrary shell access or arbitrary model-generated Python in the API process
- Kubernetes, complex RBAC/SSO, invisible chain-of-thought, or unbounded background loops
- Direct federated SQL across independent databases
- Treating checkpoint state as authoritative business memory

## Behavioral contract

The system must distinguish:

- `Confirmed`: directly supported by data or source documents
- `Inferred`: reasoned interpretation supported by correlation or domain experience
- `Unknown`: current evidence is insufficient
- `Need confirmation`: a named user or owner decision is required

Causal statements require a valid causal design. Otherwise the system may present a labeled hypothesis and a verification method only.

## Success measures

- Every material conclusion has reproducible evidence metadata.
- Every database query passes deterministic policy enforcement and is audited.
- No unapproved Skill/Memory proposal affects later behavior.
- No external write occurs without approval tied to the exact payload.
- Ambiguous material requirements are surfaced before execution.
- Each phase can run, test, demo, and roll back independently.

## Phase boundaries

| Phase | Outcome | Explicitly postponed |
|---|---|---|
| 0 | Architecture and repository rules | Runnable product |
| 1 | Chat foundation and Azure model integration | Real database analysis |
| 2 | Database, analysis, tables, and charts | Knowledge lifecycle and background reliability |
| 3 | Knowledge, Skill, and Memory | Jira/background jobs |
| 4 | Data quality, Jira interpretation, asynchronous jobs | Teams delivery |
| 5 | Teams notification and production hardening | Unbounded autonomous writes |
