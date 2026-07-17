from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ama_teammate.orchestration.graph import GraphRuntime, build_graph
from ama_teammate.orchestration.nodes import assess_goal_node
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
        assert "metric definition" in payload["missing_fields"]
        assert "time range and timezone" in payload["missing_fields"]

        resumed = await runtime.resume("run-1", "Conversion, last month UTC, approved warehouse")
        assert resumed["response_ready"] is True
        assert resumed["route"] == "analysis"
        assert resumed["clarification_response"].startswith("Conversion")
    finally:
        await connection.close()
def test_uat_total_count_routes_without_time_clarification() -> None:
    result = assess_goal_node(
        AgentState(
            schema_version="1",
            session_id="session-uat",
            run_id="run-uat",
            user_id="user-1",
            input_text="UAT 总共有多少 session",
            status="created",
        )
    )
    assert result["route"] == "analysis"
    assert result["missing_fields"] == []
def test_uat_metric_correction_uses_prior_source_context() -> None:
    result = assess_goal_node(
        AgentState(
            schema_version="2",
            session_id="session-correction",
            run_id="run-correction",
            user_id="user-1",
            input_text="Use FOC instead",
            combined_input=(
                "<conversation_history>How many Super Agent UAT sessions?"
                "</conversation_history><current_request>Use FOC instead</current_request>"
            ),
            status="created",
        )
    )
    assert result["route"] == "analysis"
    assert result["missing_fields"] == []
def test_sa_whtr_phrase_needs_no_model_clarification() -> None:
    result = assess_goal_node(
        AgentState(
            schema_version="2",
            session_id="session-sa",
            run_id="run-sa",
            user_id="user-1",
            input_text="SA\u76ee\u524dWHTR\u6574\u4f53\u662f\u591a\u5c11",
            status="created",
        )
    )
    assert result["route"] == "analysis"
    assert result["missing_fields"] == []
