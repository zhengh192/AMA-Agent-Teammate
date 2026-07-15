from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ama_teammate.domain.models import EpistemicLabel, MessageRole, RunStatus, StreamEvent
from ama_teammate.orchestration.state import AgentState
from ama_teammate.services.analysis import AnalysisService
from ama_teammate.services.chat import ChatService, encode_sse


class PhaseTwoChatService(ChatService):
    def __init__(self, *, analysis_service: AnalysisService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.analysis_service = analysis_service

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
            prepared_content = await self.prepare_input(user_id, content, run.id, session_id)
            result = await self.graph.start(
                AgentState(
                    schema_version="2",
                    session_id=session_id,
                    run_id=run.id,
                    user_id=user_id,
                    input_text=prepared_content,
                    status=RunStatus.CREATED.value,
                )
            )
            async for item in self._process_graph_result(run.id, session_id, user_id, result):
                yield item
        except Exception as exc:
            async for item in self._stream_failure(run.id, session_id, user_id, exc):
                yield item

    async def prepare_input(
        self, user_id: str, content: str, run_id: str, session_id: str
    ) -> str:
        del user_id, run_id, session_id
        return content

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
            async for item in self._process_graph_result(run.id, run.session_id, user_id, result):
                yield item
        except Exception as exc:
            async for item in self._stream_failure(run.id, run.session_id, user_id, exc):
                yield item

    async def resume_approval_stream(
        self, run_id: str, user_id: str, decision: dict[str, Any]
    ) -> AsyncIterator[str]:
        run = await self.repository.get_run(run_id)
        if run is None:
            yield encode_sse(
                StreamEvent(
                    event="error", data={"code": "run_not_found", "message": "Run not found."}
                )
            )
            return
        existing = await self.analysis_service.result_for_run(run_id)
        if existing is not None:
            async for item in self._stream_analysis_result(
                run_id, run.session_id, user_id, existing
            ):
                yield item
            return
        yield encode_sse(
            StreamEvent(event="status", data={"run_id": run_id, "status": "executing"})
        )
        try:
            result = await self.graph.resume(run_id, decision)
            if result.get("status") == "cancelled":
                await self.repository.update_run(run_id, RunStatus.CANCELLED, route="analysis")
                yield encode_sse(
                    StreamEvent(
                        event="approval.decision",
                        data={
                            "run_id": run_id,
                            "status": "cancelled",
                            "decision": str(result.get("approval_status", "rejected")),
                        },
                    )
                )
                yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run_id}))
                return
            async for item in self._process_graph_result(run_id, run.session_id, user_id, result):
                yield item
        except Exception as exc:
            async for item in self._stream_failure(run_id, run.session_id, user_id, exc):
                yield item

    async def _process_graph_result(
        self,
        run_id: str,
        session_id: str,
        user_id: str,
        result: dict[str, Any],
    ) -> AsyncIterator[str]:
        payload = self.graph.interrupt_payload(result)
        if payload is not None:
            if payload.get("kind") == "sql_approval":
                await self.repository.update_run(
                    run_id, RunStatus.WAITING_APPROVAL, route="analysis"
                )
                await self.repository.add_audit_event(
                    actor_id=user_id,
                    event_type="analysis.approval.required",
                    status="waiting",
                    session_id=session_id,
                    run_id=run_id,
                    graph_node="sql_approval",
                    safe_details={
                        "plan_id": payload.get("plan_id"),
                        "approval_id": payload.get("approval_id"),
                        "payload_hash": payload.get("payload_hash"),
                    },
                )
                yield encode_sse(StreamEvent(event="analysis.plan", data=payload))
                yield encode_sse(StreamEvent(event="approval.required", data=payload))
            else:
                await self.repository.update_run(
                    run_id, RunStatus.CLARIFYING, route=str(result.get("route", "chat"))
                )
                await self.repository.add_audit_event(
                    actor_id=user_id,
                    event_type="clarification.required",
                    status="waiting",
                    session_id=session_id,
                    run_id=run_id,
                    graph_node="clarify",
                    safe_details={"missing_fields": payload.get("missing_fields", [])},
                )
                yield encode_sse(
                    StreamEvent(
                        event="clarification.required",
                        data={"run_id": run_id, "status": "clarifying", **payload},
                    )
                )
            yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run_id}))
            return
        if result.get("route") == "analysis" and result.get("analysis_result_ref"):
            analysis_result = await self.analysis_service.result_for_run(run_id)
            if analysis_result is None:
                raise ValueError("Analysis result artifact was not found")
            async for item in self._stream_analysis_result(
                run_id, session_id, user_id, analysis_result
            ):
                yield item
            return
        async for item in self._stream_provider_response(run_id, session_id, user_id, result):
            yield item

    async def _stream_analysis_result(
        self,
        run_id: str,
        session_id: str,
        user_id: str,
        result: Any,
    ) -> AsyncIterator[str]:
        conclusions = result.computation.conclusions
        assistant_text = "\n".join(
            f"{item.epistemic_label}: {item.text} [Evidence: {', '.join(item.evidence_ids)}]"
            for item in conclusions
        )
        label = (
            EpistemicLabel.INFERRED
            if any(item.epistemic_label == EpistemicLabel.INFERRED.value for item in conclusions)
            else EpistemicLabel.CONFIRMED
        )
        messages = await self.repository.list_messages(session_id)
        if not any(
            message.run_id == run_id and message.role == MessageRole.ASSISTANT.value
            for message in messages
        ):
            await self.repository.add_message(
                session_id,
                MessageRole.ASSISTANT,
                assistant_text,
                run_id=run_id,
                epistemic_label=label.value,
            )
        await self.repository.update_run(run_id, RunStatus.COMPLETED, route="analysis")
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="run.completed",
            status="success",
            session_id=session_id,
            run_id=run_id,
            safe_details={
                "route": "analysis",
                "result_id": result.id,
                "epistemic_label": label.value,
            },
        )
        yield encode_sse(
            StreamEvent(event="message.delta", data={"run_id": run_id, "delta": assistant_text})
        )
        yield encode_sse(StreamEvent(event="analysis.result", data=result.model_dump(mode="json")))
        yield encode_sse(
            StreamEvent(
                event="run.completed",
                data={
                    "run_id": run_id,
                    "status": "completed",
                    "epistemic_label": label.value,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                },
            )
        )
        yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run_id}))
