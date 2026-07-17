from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ama_teammate.config import Settings
from ama_teammate.domain.models import (
    EpistemicLabel,
    MessageRole,
    ProviderUsage,
    RunStatus,
    StreamEvent,
)
from ama_teammate.logging import safe_error_code
from ama_teammate.orchestration.graph import GraphRuntime
from ama_teammate.orchestration.state import AgentState
from ama_teammate.providers.base import ProviderMessage
from ama_teammate.providers.factory import ProviderBundle
from ama_teammate.storage.repositories import Repository

SYSTEM_INSTRUCTIONS = """You are the Phase 1 Coordinator for AMA Data Analysis Teammate.
Never claim a database, document, tool, or external system was accessed unless the supplied context confirms it.
Do not expose chain-of-thought. Return only concise conclusions, evidence status, limitations, and next actions.
Use the labels Confirmed, Inferred, Unknown, and Need confirmation accurately.
Use prior conversation for continuity while treating earlier assistant claims as unverified.
When a safe analytical next step is apparent, propose it concretely without claiming it was executed.
Ask only for information that materially blocks the current task.
"""


def encode_sse(event: StreamEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {payload}\n\n"


class ChatService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        graph: GraphRuntime,
        providers: ProviderBundle,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.graph = graph
        self.providers = providers

    async def start_stream(self, session_id: str, user_id: str, content: str) -> AsyncIterator[str]:
        run = await self.repository.create_run(session_id, self.providers.provider.name)
        await self.repository.add_message(session_id, MessageRole.USER, content, run_id=run.id)
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="run.started",
            status="success",
            session_id=session_id,
            run_id=run.id,
            input_text=content,
            safe_details={"provider": self.providers.provider.name},
        )
        yield encode_sse(
            StreamEvent(event="run.started", data={"run_id": run.id, "status": "planning"})
        )

        try:
            await self.repository.update_run(run.id, RunStatus.PLANNING)
            result = await self.graph.start(
                AgentState(
                    schema_version="1",
                    session_id=session_id,
                    run_id=run.id,
                    user_id=user_id,
                    input_text=content,
                    status=RunStatus.CREATED.value,
                )
            )
            payload = self.graph.interrupt_payload(result)
            if payload is not None:
                await self.repository.update_run(
                    run.id, RunStatus.CLARIFYING, route=str(result.get("route", "chat"))
                )
                await self.repository.add_audit_event(
                    actor_id=user_id,
                    event_type="clarification.required",
                    status="waiting",
                    session_id=session_id,
                    run_id=run.id,
                    graph_node="clarify",
                    safe_details={"missing_fields": payload.get("missing_fields", [])},
                )
                yield encode_sse(
                    StreamEvent(
                        event="clarification.required",
                        data={"run_id": run.id, "status": "clarifying", **payload},
                    )
                )
                yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run.id}))
                return
            async for event in self._stream_provider_response(run.id, session_id, user_id, result):
                yield event
        except Exception as exc:
            async for event in self._stream_failure(run.id, session_id, user_id, exc):
                yield event

    async def resume_stream(self, run_id: str, user_id: str, content: str) -> AsyncIterator[str]:
        run = await self.repository.get_run(run_id)
        if run is None:
            yield encode_sse(
                StreamEvent(
                    event="error", data={"code": "run_not_found", "message": "Run not found."}
                )
            )
            return
        await self.repository.add_message(run.session_id, MessageRole.USER, content, run_id=run.id)
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="clarification.received",
            status="success",
            session_id=run.session_id,
            run_id=run.id,
            input_text=content,
        )
        yield encode_sse(
            StreamEvent(event="run.resumed", data={"run_id": run.id, "status": "planning"})
        )
        try:
            await self.repository.update_run(run.id, RunStatus.PLANNING)
            result = await self.graph.resume(run.id, content)
            async for event in self._stream_provider_response(
                run.id, run.session_id, user_id, result
            ):
                yield event
        except Exception as exc:
            async for event in self._stream_failure(run.id, run.session_id, user_id, exc):
                yield event

    async def _stream_provider_response(
        self,
        run_id: str,
        session_id: str,
        user_id: str,
        state: dict[str, Any],
    ) -> AsyncIterator[str]:
        route = str(state.get("route", "chat"))
        await self.repository.update_run(run_id, RunStatus.EXECUTING, route=route)
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="provider.started",
            status="running",
            session_id=session_id,
            run_id=run_id,
            graph_node="prepare_response",
            safe_details={"profile": self.providers.coordinator.name, "route": route},
        )
        yield encode_sse(
            StreamEvent(event="status", data={"run_id": run_id, "status": "executing"})
        )

        messages = [
            ProviderMessage(
                role="developer",
                content=(
                    SYSTEM_INSTRUCTIONS
                    + "\nCurrent task goal: "
                    + str(state.get("task_goal", state.get("input_text", "")))[:500]
                    + "\n"
                    + str(state.get("role_context", ""))
                ),
            ),
            ProviderMessage(
                role="user", content=str(state.get("combined_input", state.get("input_text", "")))
            ),
        ]
        chunks: list[str] = []
        usage = ProviderUsage()
        request_id: str | None = None
        async for provider_event in self.providers.provider.stream(
            messages, self.providers.coordinator
        ):
            if provider_event.delta:
                chunks.append(provider_event.delta)
                yield encode_sse(
                    StreamEvent(
                        event="message.delta",
                        data={"run_id": run_id, "delta": provider_event.delta},
                    )
                )
            if provider_event.usage is not None:
                usage = provider_event.usage
            if provider_event.request_id:
                request_id = provider_event.request_id

        assistant_text = "".join(chunks).strip()
        label = (
            EpistemicLabel.UNKNOWN
            if route in {"analysis", "knowledge"}
            else EpistemicLabel.CONFIRMED
        )
        await self.repository.add_message(
            session_id,
            MessageRole.ASSISTANT,
            assistant_text,
            run_id=run_id,
            epistemic_label=label.value,
        )
        await self.repository.update_run(
            run_id,
            RunStatus.COMPLETED,
            route=route,
            request_id=request_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="run.completed",
            status="success",
            session_id=session_id,
            run_id=run_id,
            safe_details={
                "route": route,
                "request_id": request_id,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "epistemic_label": label.value,
            },
        )
        yield encode_sse(
            StreamEvent(
                event="run.completed",
                data={
                    "run_id": run_id,
                    "status": "completed",
                    "epistemic_label": label.value,
                    "usage": usage.model_dump(),
                },
            )
        )
        yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run_id}))

    async def _stream_failure(
        self, run_id: str, session_id: str, user_id: str, exc: Exception
    ) -> AsyncIterator[str]:
        code = safe_error_code(exc)
        await self.repository.update_run(run_id, RunStatus.FAILED, error_code=code)
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="run.failed",
            status="failed",
            session_id=session_id,
            run_id=run_id,
            safe_details={"error_code": code},
        )
        yield encode_sse(
            StreamEvent(
                event="error",
                data={
                    "run_id": run_id,
                    "status": "failed",
                    "code": code,
                    "message": str(
                        getattr(
                            exc,
                            "safe_message",
                            "The run failed. Check configuration and the safe trace.",
                        )
                    ),
                },
            )
        )
        yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run_id}))
