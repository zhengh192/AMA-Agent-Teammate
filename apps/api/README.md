# AMA API

Phase 3 FastAPI/LangGraph backend with Phase 1/2 compatibility plus safe document ingestion, hybrid retrieval and citations, Knowledge conflicts, exact-approved Skills, governed Memory, and audit.

```powershell
uv run uvicorn ama_teammate.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

The default LLM and embedding providers are deterministic mocks; Azure requires environment-only configuration and a separate approved embedding deployment. Real company databases and real document scanning are not enabled.
