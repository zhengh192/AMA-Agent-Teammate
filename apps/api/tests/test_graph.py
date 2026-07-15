from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ama_teammate.orchestration.graph import GraphRuntime, build_graph
from ama_teammate.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_checkpoint_interrupt_and_resume(tmp_path: Path) -> None:
    connection = await aiosqlite.connect(tmp_path / "checkpoint.db")
    try:
        saver = AsyncSqliteSaver(connection)
        await saver.setup()
        runtime = GraphRuntime(build_graph(saver))
        initial = await runtime.start(
            AgentState(
                schema_version="1",
                session_id="session-1",
                run_id="run-1",
                user_id="user-1",
                input_text="Analyze the data",
                status="created",
            )
        )
        payload = runtime.interrupt_payload(initial)
        assert payload is not None
        assert "approved data source" in payload["missing_fields"]

        resumed = await runtime.resume("run-1", "Conversion, last month UTC, approved warehouse")
        assert resumed["response_ready"] is True
        assert resumed["route"] == "analysis"
        assert resumed["clarification_response"].startswith("Conversion")
    finally:
        await connection.close()
