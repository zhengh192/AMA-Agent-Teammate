# Super Agent UAT Source Inventory

## Coverage

- Coverage level: physical schema and bounded aggregate quality profile for the three UAT tracking
  tables; metric semantics remain draft.
- Sources checked: the 930 workbook interpretation, Git-tracked draft semantic metadata, UAT catalog,
  account privilege summary, and fixed aggregate quality queries.
- Missing high-value lanes: approved KPI formulas, timezone, Doris table-key definitions, pipeline
  ownership/lineage, retention, refresh SLA, and data-classification approval.
- Rejected or lower-confidence candidates: requirements-only 930 fields are not evidence of deployed
  columns; physical names alone are not evidence of business meaning.
- No raw business rows, credentials, transcripts, user inputs, responses, serial numbers, addresses,
  or customer payloads were persisted.

## Sources

| Source | Type | Locator | Permission Status | Last Checked | Supports | Gaps Or Caveats | Automation Eligible | Update Boundary |
|---|---|---|---|---|---|---|---|---|
| Super Agent 930 Data Requirements | Product requirements workbook | `930_Super_Agent_Data_Requirements_20260713.xlsx` | User-provided local source | 2026-07-13 | Intended datasets, fields, and KPI requirements | Version 930 fields are explicitly not implemented; workbook is not physical-schema proof | Manual | Draft proposed changes only |
| Super Agent 930 knowledge note | Source-backed interpretation | `docs/super-agent-930-knowledge.md` | Repository-readable | 2026-07-16 | Lifecycle rules, known KPI gaps, interpretation cautions | Secondary to the workbook and verified database facts | Yes | Draft proposed changes only |
| Git semantic registry | Draft structured metadata | `knowledge/data_sources/super_agent.yaml` and related files | Repository-readable | 2026-07-16 | Proposed entities, fields, relationships, and metrics | Physical names, nullability, types, and coverage conflict with UAT in several places | Yes | Must not activate without human approval |
| Super Agent UAT catalog | Doris using MySQL-compatible protocol | Logical source `super_agent_uat`; database `sa_logs`; tables `visit_log`, `turn_log`, `telemetry_log` | Authenticated `read_only` role; target database has `Select_priv`; no global privileges | 2026-07-16 | Physical tables, columns, types, nullable flags, engine, estimated rows | Endpoint does not advertise TLS; development Agent use requires the explicit A-16 exception | Development only | Physical-count aggregates only; never production |
| Super Agent UAT aggregate profile | Fixed read-only aggregate queries | Same three allowlisted tables | Same read-only role | 2026-07-16 | Counts, key uniqueness, date coverage, null rates, join coverage, non-sensitive enum counts | Snapshot only; timezone and late-arrival behavior are unknown | Development only | Approved physical-count definitions only; never auto-activate business KPIs |

## Source precedence

1. Verified UAT physical facts control table existence, physical names, types, and observed quality.
2. Approved product/data-owner definitions control business meaning and metric formulas.
3. The 930 workbook controls intended future requirements but not current availability.
4. Repository interpretations and model inferences remain explicitly labeled and cannot overwrite
   approved definitions.

## Current access boundary

- Agent SQL routing is opt-in for development. Physical counts are authoritative; supported 930 draft formulas may run as visible, correctable working assumptions labeled Inferred.
- Sensitive payload-like columns must be denied before any row-level query is enabled.
- The plaintext UAT exception is reusable only in development; production configuration rejects it.
- Automated refresh is not eligible until a TLS-enabled endpoint or approved encrypted tunnel exists.
