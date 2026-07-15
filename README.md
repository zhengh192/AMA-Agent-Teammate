# AMA Data Analysis Teammate

> Enterprise data analysis teammate powered by a controlled LangGraph workflow.

AMA Data Analysis Teammate is an internal, governed analytics application. **Phase 3 is runnable**:

`React chat -> FastAPI -> typed LangGraph -> governed analysis + document ingestion -> hybrid retrieval/citations -> exact Skill/Memory approval -> SQLite audit`

AMA Data Analysis Teammate 是面向企业内部的数据分析数字同事。当前已完成 **Phase 2：数据库、受控分析、表格和图表**；真实公司数据库、Knowledge、Jira、后台任务和外部通知仍保持禁用。

## Phase 3 capabilities

- Phase 1 sessions, persistent chat, SSE streaming, clarification/resume, Azure/Mock providers, checkpoints, and trace
- Phase 2 read-only SQL, approvals, cross-source joins, controlled analysis, Plotly charts, and evidence
- PDF/DOCX/XLSX/CSV/TXT/Markdown ingestion with versioned page/sheet/section/row/line citations
- Mock/Azure embedding abstraction and authorization-filtered hybrid retrieval; no source returns `Unknown`
- Structured Knowledge conflicts surfaced as `Need confirmation`
- Git-tracked, versioned Skill proposals with exact-hash approval, allowlists, deprecation, rollback, and invocation audit
- Versioned Memory proposal, approval, correction, expiry, secret rejection, and deletion lifecycle
- Named PostgreSQL/MySQL/SQL Server dialect demo sources with read-only handles, allowlists, denied columns, limits, health, and redaction
- Structured analysis intent plus deterministic metric/table resolution and SQL generation
- SQLGlot AST validation, exact-payload approval interrupt/resume, bounded execution, and audit
- Independent source queries plus in-memory DuckDB joins with coercion, duplicate, match, and unmatched metrics
- Controlled trend, comparison, segment, contribution, funnel/rate, quality, anomaly, calendar hypothesis, and correlation functions
- Validated Plotly table, KPI, line, bar, stacked bar, scatter, histogram, and heatmap specifications
- Result table, evidence-linked conclusions, trace, safe errors, and ownership-checked bounded CSV download

No arbitrary model-generated Python is executed. Phase 4 has not started.

## Prerequisites

- Python 3.12 or 3.13
- `uv`
- Node.js 22+ and `pnpm` 11+
- Google Chrome for the configured Playwright project

## Install

```powershell
uv sync
pnpm install
```

## Start locally

Terminal 1 — API:

```powershell
uv run uvicorn ama_teammate.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

Terminal 2 — web:

```powershell
pnpm --dir apps/web dev
```

Open `http://127.0.0.1:5173`. Runtime databases and artifacts are written under ignored `var/` paths.

For deterministic demos, set `AMA_PROVIDER=mock`. Azure uses provider boundaries and environment-only configuration; model output and embeddings remain untrusted inputs. Keep `AMA_EMBEDDING_PROVIDER=mock` unless an approved Azure embedding deployment is configured.

## Demo prompts

1. `Query revenue trend for 2025 from the PostgreSQL sales data source.`
2. `Analyze the data.` — must clarify and execute no SQL.
3. `Run a data query for revenue by channel across PostgreSQL and MySQL for 2025.`
4. The first prompt produces a line chart.
5. `Analyze data revenue contribution by segment with a stacked chart for 2025 from PostgreSQL.`
6. `Analyze conversion rate data completeness, missing and duplicate rows for 2025 from SQL Server.`
7. `Data query: why is revenue correlated with marketing spend in 2025 using PostgreSQL and MySQL?` — must remain `Inferred`, not causal.

Review the plan and SQL, then choose **Approve and execute**. See `docs/phase-2-implementation.md` for analysis demos and `docs/phase-3-implementation.md` for Knowledge/Skill/Memory workflows and security limitations.

## Test

```powershell
uv run ruff check .
uv run mypy apps/api/src
uv run pytest
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
pnpm --dir apps/web test:e2e
```

Playwright starts an isolated Mock Provider environment and does not use local Azure credentials.

## Azure OpenAI

Copy `.env.example` to `.env`, set `AMA_PROVIDER=azure`, and provide approved endpoint, API version, deployment, and authentication values. Entra ID is preferred; API key mode is development-only.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/provider/smoke
```

The response never echoes credentials or endpoint configuration.

## API summary

- `GET /api/health`, `GET /api/ready`, `POST /api/provider/smoke`
- `POST/GET /api/sessions`, messages, SSE chat, clarification resume, and trace
- `GET /api/data-sources`
- `POST /api/runs/{run_id}/approval/stream`
- `GET /api/runs/{run_id}/analysis`
- `GET /api/artifacts/{artifact_id}/download`
- `POST /api/documents/upload`, `GET /api/documents`, `POST /api/knowledge/ask`, conflicts
- Skill and Memory proposal, exact decision, lifecycle, and embedding smoke endpoints

## Security boundary

The included databases are synthetic local SQLite files that emulate PostgreSQL/MySQL/SQL Server dialect policies. They are not real enterprise connectors. Real sources require approved read-only identities, schema/table/column policy, secrets management, classification, retention, and threat-model review.

## License

Private/internal by default. No open-source license is granted and no MIT `LICENSE` is present.
