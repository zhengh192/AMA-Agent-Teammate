from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi.testclient import TestClient


def parse_sse(lines: Iterator[str]) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event_name = "message"
    for line in lines:
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event_name, json.loads(line.removeprefix("data: "))))
    return events


def create_session(client: TestClient) -> str:
    response = client.post("/api/sessions", json={"title": "Phase 1 test"})
    assert response.status_code == 201
    return str(response.json()["id"])


def test_health_readiness_and_session_persistence(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    readiness = client.get("/api/ready")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"

    session_id = create_session(client)
    sessions = client.get("/api/sessions").json()
    assert sessions[0]["id"] == session_id
    assert sessions[0]["title"] == "Phase 1 test"


def test_mock_chat_stream_persists_messages_and_trace(client: TestClient) -> None:
    session_id = create_session(client)
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": "Hello teammate"},
    ) as response:
        assert response.status_code == 200
        events = parse_sse(response.iter_lines())

    names = [name for name, _ in events]
    assert "message.delta" in names
    assert "run.completed" in names
    run_id = str(next(data["run_id"] for name, data in events if name == "run.started"))

    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["epistemic_label"] == "Confirmed"
    assert "Mock Provider" in messages[-1]["content"]

    trace = client.get(f"/api/runs/{run_id}/trace")
    assert trace.status_code == 200
    assert [event["event_type"] for event in trace.json()] == [
        "run.started",
        "provider.started",
        "run.completed",
    ]


def test_ambiguous_analysis_interrupts_and_resumes(client: TestClient) -> None:
    session_id = create_session(client)
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": "请分析一下数据为什么下降"},
    ) as response:
        events = parse_sse(response.iter_lines())

    clarification = next(data for name, data in events if name == "clarification.required")
    run_id = str(clarification["run_id"])
    assert set(clarification["missing_fields"]) == {
        "metric definition",
        "time range and timezone",
    }
    assert not any(name == "message.delta" for name, _ in events)

    with client.stream(
        "POST",
        f"/api/runs/{run_id}/resume/stream",
        json={"content": "Conversion rate, last month in UTC, from the approved warehouse."},
    ) as response:
        assert response.status_code == 200
        resumed_events = parse_sse(response.iter_lines())

    approval = next(data for name, data in resumed_events if name == "approval.required")
    assert approval["status"] == "waiting_approval"
    assert approval["plan"]["queries"]
    assert not any(name == "run.completed" for name, _ in resumed_events)
    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert [message["role"] for message in messages] == ["user", "user"]


def test_session_ownership_is_enforced(client: TestClient) -> None:
    response = client.get("/api/sessions/not-a-session/messages")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_provider_smoke_uses_safe_mock_result(client: TestClient) -> None:
    response = client.post("/api/provider/smoke")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "mock",
        "deployment": "mock-coordinator",
        "request_id": None,
        "error_code": None,
        "safe_message": None,
    }
