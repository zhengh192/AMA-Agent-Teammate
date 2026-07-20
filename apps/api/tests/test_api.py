from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi.testclient import TestClient

from ama_teammate.domain.models import ProviderEvent, ProviderUsage


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
    assert "我结合前面的对话" in messages[-1]["content"]
    assert "<current_request>" not in messages[-1]["content"]

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
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == clarification["question"]
    assert messages[1]["epistemic_label"] == "Need confirmation"


def test_session_ownership_is_enforced(client: TestClient) -> None:
    response = client.get("/api/sessions/not-a-session/messages")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_deleted_session_is_hidden_and_no_longer_accessible(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert session_id not in {item["id"] for item in client.get("/api/sessions").json()}
    missing = client.get(f"/api/sessions/{session_id}/messages")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "session_not_found"
    assert client.delete(f"/api/sessions/{session_id}").status_code == 404

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


def test_empty_provider_stream_uses_nonempty_audited_fallback(
    client: TestClient, monkeypatch
) -> None:
    provider = client.app.state.providers.provider

    async def empty_stream(self, messages, profile):
        del self, messages, profile
        yield ProviderEvent(
            event_type="response.completed",
            usage=ProviderUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )

    monkeypatch.setattr(type(provider), "stream", empty_stream)
    session_id = create_session(client)
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": "Hello after an empty provider response"},
    ) as response:
        assert response.status_code == 200
        events = parse_sse(response.iter_lines())

    deltas = [str(data["delta"]) for name, data in events if name == "message.delta"]
    assert deltas
    assert "".join(deltas).strip()
    run_id = str(next(data["run_id"] for name, data in events if name == "run.started"))
    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert messages[-1]["content"].strip()
    assert messages[-1]["epistemic_label"] == "Unknown"
    trace = client.get(f"/api/runs/{run_id}/trace").json()
    assert "provider.empty_response" in [event["event_type"] for event in trace]
