from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ama_teammate.analysis.models import AnalysisNarrative, NarrativeClaim
from ama_teammate.config import Settings
from ama_teammate.orchestration.nodes import assess_goal_node, build_assess_goal_node
from ama_teammate.orchestration.state import AgentState
from ama_teammate.providers.factory import create_provider_bundle
from ama_teammate.services.context import (
    build_conversation_context,
    select_relevant_skills,
)
from ama_teammate.services.phase2_chat import PhaseTwoChatService


def _state(text: str) -> AgentState:
    return AgentState(
        schema_version="2",
        session_id="session-1",
        run_id="run-1",
        user_id="user-1",
        input_text=text,
        combined_input=text,
        status="created",
    )


def test_multilingual_analysis_routing_does_not_require_source_name() -> None:
    result = assess_goal_node(
        _state("\u5206\u6790\u6700\u8fd1\u4e00\u4e2a\u6708 conversion \u8d8b\u52bf")
    )

    assert result["route"] == "analysis"
    assert result["missing_fields"] == []


def test_ambiguous_analysis_requests_only_material_definition_and_time() -> None:
    result = assess_goal_node(_state("\u8bf7\u5206\u6790\u6570\u636e"))

    assert result["route"] == "analysis"
    assert result["missing_fields"] == [
        "metric definition",
        "time range and timezone",
    ]


@pytest.mark.asyncio
async def test_model_assisted_goal_assessment_uses_provider_abstraction() -> None:
    providers = create_provider_bundle(Settings(_env_file=None, ama_provider="mock"))
    node = build_assess_goal_node(providers)

    result = await node(
        _state("\u67e5\u770b\u6700\u8fd1\u4e00\u4e2a\u6708 conversion \u8d8b\u52bf")
    )

    assert result["route"] == "analysis"
    assert result["missing_fields"] == []
    assert result["decision_summary"] == "Mock structured goal classification."


@pytest.mark.asyncio
async def test_goal_assessment_ignores_retrieved_context_markers() -> None:
    providers = create_provider_bundle(Settings(_env_file=None, ama_provider="mock"))
    node = build_assess_goal_node(providers)
    state = _state("Hello")
    state["combined_input"] = (
        "<approved_knowledge_context>data metric analysis</approved_knowledge_context>"
        "\n<current_request>Hello</current_request>"
    )

    result = await node(state)

    assert result["route"] == "chat"
    assert result["missing_fields"] == []


def test_conversation_context_is_bounded_redacted_and_excludes_current_run() -> None:
    messages = [
        SimpleNamespace(run_id="run-1", role="user", content="Project Orion password=plain-secret"),
        SimpleNamespace(run_id="run-1", role="assistant", content="Orion is the current project."),
        SimpleNamespace(run_id="run-2", role="user", content="What is my current project?"),
    ]

    context = build_conversation_context(
        messages,
        current_run_id="run-2",
        max_messages=2,
        max_characters=500,
    )

    assert context.message_count == 2
    assert "Project Orion" in context.text
    assert "plain-secret" not in context.text
    assert "[REDACTED]" in context.text
    assert "What is my current project?" not in context.text

    disabled = build_conversation_context(
        messages,
        current_run_id="run-2",
        max_messages=0,
        max_characters=500,
    )
    assert disabled.message_count == 0
    assert disabled.text == ""


def test_user_taught_skill_selection_is_content_based_not_name_based() -> None:
    skills = [
        {
            "name": "team-method-42",
            "version": "3",
            "instructions": "When conversion declines, check completeness and then segment by Geo.",
        },
        {
            "name": "unrelated-export",
            "version": "1",
            "instructions": "Format a weekly inventory export.",
        },
    ]

    selected = select_relevant_skills("Why did conversion decline by Geo?", skills)

    assert [skill["name"] for skill in selected] == ["team-method-42"]


def test_analysis_narrative_rejects_unknown_evidence_ids() -> None:
    narrative = AnalysisNarrative(
        executive_summary="Summary",
        confirmed_findings=[NarrativeClaim(text="Unsupported claim", evidence_ids=["invented"])],
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        PhaseTwoChatService._validate_narrative_evidence(narrative, {"evidence-1"})


def _stream_payloads(client: TestClient, session_id: str, content: str) -> list[dict[str, object]]:
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": content},
    ) as response:
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    return payloads


def test_second_turn_receives_bounded_conversation_context(client: TestClient) -> None:
    session = client.post("/api/sessions", json={"title": "Continuity"}).json()
    session_id = str(session["id"])
    _stream_payloads(client, session_id, "Remember that my current project is Orion.")

    payloads = _stream_payloads(client, session_id, "What is my current project?")

    deltas = [str(item["delta"]) for item in payloads if "delta" in item]
    assert "Orion" in "".join(deltas)
    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    run_id = messages[-1]["run_id"]
    trace = client.get(f"/api/runs/{run_id}/trace").json()
    context_events = [
        event for event in trace if event["event_type"] == "conversation.context.assembled"
    ]
    assert len(context_events) == 1
    assert context_events[0]["safe_details"]["message_count"] == 2
