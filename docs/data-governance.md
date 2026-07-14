# Data Governance

## Principles

- Purpose limitation and least privilege
- Data minimization before model or analysis use
- Source/version/effective-date provenance
- Explicit classification and owner accountability
- Human approval for durable behavior changes and external delivery
- Retention, deletion, and legal-hold policy by record class
- Evidence that is reproducible without unnecessarily duplicating sensitive data

## Data classes

The enterprise owner must map company policy to these initial technical classes:

| Class | Example | Default handling |
|---|---|---|
| Public | Approved public documentation | Normal controls |
| Internal | Internal process descriptions | Authenticated access; no public sharing |
| Confidential | Business metrics, issue details | Need-to-know, encrypted, redacted logs |
| Restricted | PII, secrets, regulated data | Deny by default; explicit field policy and owner approval |

Secrets are never analytical data and must not enter prompts, checkpoints, artifacts, Knowledge, or Memory.

## Data-source onboarding

No source is usable until an owner approves:

- logical name, system owner, data steward, business purpose, environment
- database type and secret reference
- data classification and permitted user groups/purposes
- allowed schemas/tables/views and denied/sensitive columns
- timezone, freshness expectations, retention, and known quality limitations
- query timeout, max rows, max bytes, concurrency/cost constraints
- verified read-only identity and revocation procedure
- sample/mock data and acceptance tests

Configuration is versioned. Every query audit references the effective source-policy version.

## Query and result lifecycle

1. Confirm purpose, metric definition, time window/timezone, dimensions, source, and success criteria.
2. Minimize fields, rows, and time range; prefer source-side aggregation.
3. Validate access and SQL policy, then obtain approval when required.
4. Execute, record lineage and quality metadata, and classify the result.
5. Use a bounded protected artifact for analysis; avoid raw-row persistence.
6. Produce evidence references and derived aggregates.
7. Delete temporary DuckDB/results on completion/expiry unless an approved retention need exists.

Query results do not become Knowledge or Memory automatically.

## Cross-source governance

Before joining sources, verify compatible purposes/classifications, approved join keys, identity resolution rules, expected cardinality, and whether the combination increases sensitivity. Record source-specific query lineage and local transformation lineage. Reject or escalate joins that are large, many-to-many unexpectedly, or likely to reveal denied attributes.

## Document governance

Each document records source file, content hash, uploader, owner, version, effective date, classification, page/sheet/section, parser version, scan status, and lifecycle status. Chunks remain traceable to exact source locations. Superseded or withdrawn material is excluded by default but retained according to policy/audit needs.

Document ingestion creates proposals; it never silently activates business rules, Skills, or Memory.

## Evidence and claims

Each important claim links to:

- source database/document and policy-approved identifier
- SQL/retrieval query and parameters/filters in an appropriately protected form
- dataset/document version and time
- fields, calculation method, and supporting aggregate/artifact
- freshness/quality limitations
- confidence and `Confirmed`/`Inferred` label

`Unknown` is required where evidence is insufficient. `Need confirmation` identifies the responsible person/owner when possible.

## Retention schedule to approve

No production values are assumed. Before real data, owners must set and implement retention for:

- sessions/messages
- LangGraph checkpoints
- uploads and parsed content
- query results/DuckDB workspaces
- charts/reports
- audit/security events
- Knowledge and source versions
- Skill and Memory proposals/approvals
- jobs and notification delivery receipts

Deletion propagates to derived artifacts/indexes while preserving minimum legally required audit facts. Legal hold overrides normal deletion through an explicit governed process.

## Data subject and correction handling

When policy applies, provide discoverability, correction, access restriction, and deletion mechanisms for personal data across sources, uploads, indexes, artifacts, and Memory. A source correction should invalidate or mark dependent evidence and derived conclusions stale.

## Quality governance

Record freshness, row/volume completeness, nulls, duplicates, referential integrity, expected ranges, distribution drift, missing partitions, pipeline delay, and applicable incident windows. Quality failures reduce confidence or stop the analysis; they are not hidden by model narrative.

## Ownership

| Role | Accountability |
|---|---|
| Product owner | Product scope, success criteria, phase acceptance |
| Data owner | Purpose, access, classification, retention, metric authority |
| Data steward | Catalog, field definitions, quality and provenance |
| Security/privacy | Threat controls, restricted data, incident and legal requirements |
| Skill/Knowledge owner | Proposal approval, version, deprecation |
| Platform operator | Availability, backup, restore, deletion execution |
