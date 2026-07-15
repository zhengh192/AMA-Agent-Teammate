# Phase 2 Implementation Notes

## Outcome

Phase 2 extends the Phase 1 modular monolith with a governed Data Analyst subgraph:

`natural-language question -> clarification -> structured intent -> deterministic metric/table resolution -> SQLGlot validation -> exact-payload approval interrupt -> read-only execution -> optional DuckDB join -> controlled analysis -> validated Plotly JSON -> evidence-linked result`

The top-level LangGraph remains the only orchestration application. Its checkpoint contains bounded references (`plan_ref`, query proposal refs, approval ref, result ref), while plans, SQL, approvals, executions, datasets, evidence, and artifacts are authoritative records outside the checkpoint.

## Local demo sources

No approved company database, read-only identity, schema allowlist, denied-column policy, or representative company data was supplied. Phase 2 therefore enables only local deterministic demo connectors:

| Source id | Declared dialect | Local demo tables | Denied columns |
|---|---|---|---|
| `sales_postgres` | PostgreSQL | `daily_sales`, `segment_sales` | `customer_email` |
| `marketing_mysql` | MySQL | `campaigns` | `owner_token` |
| `operations_sqlserver` | SQL Server | `funnel_events` | `user_phone` |

Each connector opens its SQLite demo database with `mode=ro` and `PRAGMA query_only=ON`. The dialect label drives SQLGlot parsing and policy fixtures; it is not a claim that a real PostgreSQL, MySQL, or SQL Server instance was contacted. Real drivers and credentials remain disabled until data-owner and security approval supplies the required configuration.

## Security boundaries

- Only a single `SELECT` statement is accepted. SQL comments, wildcards, multi-statements, DML, DDL, transactions, commands, unapproved tables/schemas/columns, denied columns, parameter mismatches, and excessive limits fail closed.
- SQL is parsed as an AST with SQLGlot; keyword filtering is not the authorization control.
- Approval binds normalized SQL, parameters, source, row/byte/time limits, join plan, and policy version by SHA-256 payload hash.
- Changed or replayed approval payloads cannot execute. A syntax repair is attempted at most once as a proposal; changed SQL stops and requires a new approval.
- Execution uses read-only database handles plus timeout, row, and byte caps. Audit stores actual normalized SQL in the classified query-execution record and safe hashes/metrics in ordinary trace events.
- Cross-source queries execute independently. Only bounded results enter an in-memory DuckDB connection with external access disabled. Join keys, string coercion, duplicates, match rates, and weak-quality warnings are recorded.
- Analysis uses versioned allowlisted Python functions. No model-generated Python is executed, and the API process never calls `exec` on model output.
- Plotly specifications use an allowlist for table, indicator/KPI, scatter/line, bar, stacked bar, histogram, and heatmap traces, with a 5,000-point cap and active-content rejection. Invalid chart proposals fall back to a table.
- CSV export is bounded, ownership-checked, stored under the configured artifact root, and prefixes spreadsheet formula characters.
- Model structured output is untrusted. Source resolution, SQL templates, AST policy, approval, execution, calculations, evidence linkage, and chart validation are deterministic.

## Controlled analysis library

The versioned `controlled-analysis-v1` library supports trend, period comparison, segment breakdown, contribution, funnel/rate, missing/null/duplicate checks, basic z-score change detection, calendar/seasonality hypotheses, and Pearson correlation. Correlation and calendar explanations are labeled `Inferred`; causal wording is blocked without an approved causal design.

## Demo

Run with the deterministic provider:

```powershell
$env:AMA_PROVIDER="mock"
uv run uvicorn ama_teammate.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
pnpm --dir apps/web dev
```

Open `http://127.0.0.1:5173`, create a session, submit a prompt, review the exact SQL, and choose **Approve and execute**.

| Case | Prompt | Expected behavior |
|---|---|---|
| Single source / line | `Query revenue trend for 2025 from the PostgreSQL sales data source.` | Approval, 12-row result, line chart, CSV, evidence |
| Ambiguous metric | `Analyze the data.` | Clarification interrupt; no SQL executes |
| Cross database | `Run a data query for revenue by channel across PostgreSQL and MySQL for 2025.` | Two independent queries, DuckDB join, unmatched-quality warning |
| Line chart | Same as single source | Validated Plotly line spec |
| Stacked contribution | `Analyze data revenue contribution by segment with a stacked chart for 2025 from PostgreSQL.` | Stacked bar, shares, reconciliation gap |
| Completeness | `Analyze conversion rate data completeness, missing and duplicate rows for 2025 from SQL Server.` | Confirmed null/duplicate evidence |
| Non-causal explanation | `Data query: why is revenue correlated with marketing spend in 2025 using PostgreSQL and MySQL?` | Scatter, Pearson association, `Inferred` causal caveat |

## Limitations and postponed work

- Real PostgreSQL/MySQL/SQL Server network connectors are not enabled because no approved sources or read-only credentials were supplied.
- The demo planner covers the approved demo metric catalog. Production semantic metric definitions and schema owners remain unknown.
- Local result JSON/CSV artifacts are internal, bounded, and Git-ignored, but production retention/deletion, encryption, malware controls, object storage, and classification enforcement remain unresolved.
- The development identity can approve its own local demo query. Production separation of requester/approver and enterprise authorization is postponed pending identity design.
- Plotly.js is a large lazy-loaded browser chunk; production performance optimization remains a hardening item.
- Arbitrary generated Python, uploads/Knowledge, Jira/jobs, and notifications remain disabled. Phase 3 has not started.

## Rollback

Set `AMA_PROVIDER=mock`, stop the API, remove ignored `var/demo-databases`, `var/artifacts`, and Phase 2-only local metadata if required, then revert the Phase 2 code/migration checkpoint. Phase 1 chat routes and message/checkpoint tables remain compatible.
