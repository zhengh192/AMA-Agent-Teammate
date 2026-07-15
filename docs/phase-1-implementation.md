# Phase 1 Implementation Notes

## Implemented

- React/Vite/TypeScript chat UI with sessions, streamed messages, status, plan/trace panels, responsive layout, and an intentionally disabled upload placeholder.
- FastAPI health/readiness, session/message, SSE stream, resume, trace, and provider smoke endpoints.
- Typed LangGraph Coordinator flow with deterministic intent/completeness checks and SQLite-backed `interrupt()` / `Command(resume=...)` clarification.
- Mock and Azure OpenAI provider adapters with environment-only deployment/auth configuration, streaming, timeout/retry, request ID and token usage capture, and safe smoke results.
- SQLite metadata and audit schema for all Phase 1 records plus a separate LangGraph checkpoint database.
- Phase 1 Data Analyst and Knowledge Curator interfaces that explicitly prohibit claims of database/document access.

## Local security boundary

The development identity is a single configured local user. It is not production authentication. Uploaded files, database connectors, SQL, RAG, arbitrary Python, background jobs, and external writes remain disabled.

The API stores message content because persistent chat is a Phase 1 requirement. Audit events store hashes and bounded metadata rather than prompt content. Checkpoints contain bounded orchestration state only; approval and audit records remain authoritative outside the checkpoint.

## Azure smoke test

Set `AMA_PROVIDER=azure` and the approved Azure variables in a local `.env`, start the API, then call:

```bash
curl -X POST http://127.0.0.1:8000/api/provider/smoke
```

The response contains only provider/deployment, success state, safe request ID/error code, and a sanitized message. It does not echo endpoint, credentials, tokens, or response content.

## Postponed

- Phase 2: database catalog/connectors, SQL generation/validation/execution, DuckDB, analysis, charts.
- Phase 3: real upload processing, document retrieval, Knowledge/Skill/Memory activation.
- Phase 4+: background jobs, Jira, notifications, production identity and hardening.

## Sources

- [Official OpenAI Python SDK and Azure configuration](https://github.com/openai/openai-python)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
