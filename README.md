# AMA Data Analysis Teammate

> Enterprise data analysis teammate powered by a controlled LangGraph workflow.

AMA Data Analysis Teammate is an internal-facing assistant for natural-language analytics, governed database access, evidence-linked findings, document knowledge, and approval-controlled background work. This repository currently contains the **Phase 0 architecture and repository baseline only**. It does not yet contain a runnable product.

AMA Data Analysis Teammate 是面向企业内部的数据分析数字同事，目标是通过自然语言接受分析任务，在受控权限下访问数据、生成可追溯结论，并通过人工审批管理有副作用的操作。当前仓库仅完成 **Phase 0：架构与仓库规则**，尚未进入应用实现阶段。

## Status

- Phase: `0 - Architecture and repository rules`
- Runtime decision: LangGraph OSS Python library only
- Default LLM provider: company Azure OpenAI deployment, configured by environment
- Default metadata store for local MVP: SQLite behind storage interfaces
- External writes: prohibited in MVP unless a future phase adds an explicit approval-controlled integration
- License: proprietary/internal by default; no open-source license has been granted

## Phase 0 deliverables

The design baseline lives in [`docs/`](docs/):

- Product boundary and phased delivery
- System and LangGraph architecture
- Security, data governance, and data model
- Knowledge, Skill, and Memory governance
- Observability and audit requirements
- Licensing rules and assumptions
- Development plan and MVP acceptance criteria

## Proposed repository tree

```text
.
├── AGENTS.md
├── README.md
├── THIRD_PARTY_NOTICES.md
├── .env.example
├── .gitignore
├── apps/
│   ├── api/                 # Phase 1 FastAPI application and graph runtime
│   │   └── src/ama_teammate/
│   └── web/                 # Phase 1 React/Vite/TypeScript user interface
├── docs/                    # Architecture and governance source of truth
├── infra/                   # Local reproducibility; no Kubernetes in MVP
├── skills/                  # Approved, versioned business Skills
├── tests/                   # Cross-component and end-to-end tests
└── var/                     # Runtime-only local data; ignored by Git
```

## Planned local commands

These commands are targets for Phase 1 and are not expected to work yet:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy apps/api/src
pnpm --dir apps/web install
pnpm --dir apps/web test
pnpm --dir apps/web build
```

## Configuration

Copy `.env.example` to a local `.env` only after Phase 1 introduces runnable services. Never commit `.env`, API keys, database connection strings, tokens, customer data, or exported query results.

The Azure model value is a **deployment name**, not a public model ID. Different logical agents can receive different deployment profiles without changing business code.

## Architecture principles

1. Deterministic policy, permission, SQL, evidence, and approval nodes guard model-driven work.
2. Databases use genuinely read-only identities plus schema/table/column policy enforcement.
3. Cross-source analysis executes bounded queries independently, then joins limited results in DuckDB.
4. LangGraph checkpoints are execution state, not the system of record for Knowledge, Skills, Memory, approvals, or audit.
5. Every material finding is linked to reproducible evidence and labeled `Confirmed`, `Inferred`, `Unknown`, or `Need confirmation`.
6. Uploaded documents and tool outputs are untrusted input.
7. No arbitrary model-generated Python runs in the FastAPI process.

## Before Phase 1

The blocking decisions are listed in [`docs/assumptions.md`](docs/assumptions.md). Phase 1 must not start until the owner confirms the Azure API/auth configuration, identity model, data classification baseline, retention rules, and initial deployment environment.

## References

- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
