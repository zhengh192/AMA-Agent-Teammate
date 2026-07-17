from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ama_teammate.analysis.models import AnalysisNarrative, NarrativeClaim
from ama_teammate.domain.models import EpistemicLabel, MessageRole, RunStatus, StreamEvent
from ama_teammate.orchestration.state import AgentState
from ama_teammate.providers.base import ProviderMessage, StructuredProviderRequest
from ama_teammate.services.analysis import AnalysisService
from ama_teammate.services.chat import ChatService, encode_sse
from ama_teammate.services.context import build_conversation_context

ANALYSIS_SYNTHESIS_INSTRUCTIONS = """Synthesize an executive analysis narrative from only the
validated evidence payload supplied by the application. Every finding must cite one or more
provided evidence IDs. Preserve Confirmed versus Inferred boundaries and never turn correlation
or a hypothesis into causation. State material unknowns and limitations. Recommend only bounded
next analytical actions; do not claim they were executed. Return conclusions, not chain-of-thought.
"""


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
            if "<current_request>" not in prepared_content:
                prepared_content = f"<current_request>\n{prepared_content}\n</current_request>"
            history = build_conversation_context(
                await self.repository.list_messages(session_id),
                current_run_id=run.id,
                max_messages=self.settings.ama_conversation_history_max_messages,
                max_characters=self.settings.ama_conversation_history_max_characters,
            )
            if history.message_count:
                prepared_content = f"{history.text}\n\n{prepared_content}"
                await self.repository.add_audit_event(
                    actor_id=user_id,
                    event_type="conversation.context.assembled",
                    status="success",
                    session_id=session_id,
                    run_id=run.id,
                    safe_details={
                        "message_count": history.message_count,
                        "character_count": history.character_count,
                    },
                )
            result = await self.graph.start(
                AgentState(
                    schema_version="2",
                    session_id=session_id,
                    run_id=run.id,
                    user_id=user_id,
                    input_text=content,
                    combined_input=prepared_content,
                    status=RunStatus.CREATED.value,
                )
            )
            async for item in self._process_graph_result(run.id, session_id, user_id, result):
                yield item
        except Exception as exc:
            async for item in self._stream_failure(run.id, session_id, user_id, exc):
                yield item

    async def prepare_input(self, user_id: str, content: str, run_id: str, session_id: str) -> str:
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
        label = (
            EpistemicLabel.INFERRED
            if any(item.epistemic_label == EpistemicLabel.INFERRED.value for item in conclusions)
            else EpistemicLabel.CONFIRMED
        )
        messages = await self.repository.list_messages(session_id)
        question = next(
            (
                str(message.content)
                for message in messages
                if message.run_id == run_id and message.role == MessageRole.USER.value
            ),
            "",
        )
        narrative, synthesized = await self._create_analysis_narrative(result, question)
        assistant_text = self._render_analysis_narrative(narrative)
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
            event_type=(
                "analysis.synthesis.completed" if synthesized else "analysis.synthesis.fallback"
            ),
            status="success",
            session_id=session_id,
            run_id=run_id,
            safe_details={
                "result_id": result.id,
                "evidence_ids": [item.id for item in self._result_evidence(result)],
            },
        )
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
        for index in range(0, len(assistant_text), 120):
            yield encode_sse(
                StreamEvent(
                    event="message.delta",
                    data={"run_id": run_id, "delta": assistant_text[index : index + 120]},
                )
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

    async def _create_analysis_narrative(
        self, result: Any, question: str
    ) -> tuple[AnalysisNarrative, bool]:
        fallback = self._fallback_analysis_narrative(result)
        if (
            not self.settings.ama_analysis_synthesis
            or "super_agent_uat" in result.data_source_references
        ):
            return fallback, False
        evidence = self._result_evidence(result)
        payload = {
            "question": question[:2_000],
            "executive_summary": result.executive_summary,
            "conclusions": [
                item.model_dump(mode="json") for item in result.computation.conclusions
            ],
            "evidence": [
                {
                    "id": item.id,
                    "title": item.title,
                    "epistemic_label": item.epistemic_label,
                    "confidence": item.confidence,
                    "limitations": item.limitations,
                }
                for item in evidence
            ],
            "data_quality": [
                {"dataset_id": dataset.id, **dataset.quality.model_dump(mode="json")}
                for dataset in result.datasets
            ],
            "join_quality": (
                result.join_quality.model_dump(mode="json") if result.join_quality else None
            ),
            "unknowns": result.unknowns,
            "recommendations": result.recommendations,
            "limitations": result.limitations,
            "metric_references": [
                item.model_dump(mode="json") for item in result.metric_references
            ],
            "skill_references": [item.model_dump(mode="json") for item in result.skill_references],
        }
        try:
            response = await self.providers.provider.generate_structured(
                [
                    ProviderMessage(role="developer", content=ANALYSIS_SYNTHESIS_INSTRUCTIONS),
                    ProviderMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    ),
                ],
                self.providers.analyst,
                StructuredProviderRequest(name="analysis_narrative", schema=AnalysisNarrative),
            )
            if not isinstance(response, AnalysisNarrative):
                raise TypeError("Provider returned an invalid analysis narrative")
            self._validate_narrative_evidence(response, {item.id for item in evidence})
            return response, True
        except Exception:
            return fallback, False

    @staticmethod
    def _result_evidence(result: Any) -> list[Any]:
        return list(result.evidence or result.computation.evidence)

    @staticmethod
    def _fallback_analysis_narrative(result: Any) -> AnalysisNarrative:
        confirmed: list[NarrativeClaim] = []
        inferred: list[NarrativeClaim] = []
        for conclusion in result.computation.conclusions:
            if not conclusion.evidence_ids:
                continue
            claim = NarrativeClaim(text=conclusion.text, evidence_ids=list(conclusion.evidence_ids))
            if conclusion.epistemic_label == EpistemicLabel.INFERRED.value:
                inferred.append(claim)
            else:
                confirmed.append(claim)
        return AnalysisNarrative(
            executive_summary=result.executive_summary
            or "The approved analysis completed with evidence-linked results.",
            confirmed_findings=confirmed,
            inferred_findings=inferred,
            unknowns=list(result.unknowns),
            next_actions=list(result.recommendations),
            limitations=list(result.limitations),
        )

    @staticmethod
    def _validate_narrative_evidence(
        narrative: AnalysisNarrative, allowed_evidence_ids: set[str]
    ) -> None:
        claims = [*narrative.confirmed_findings, *narrative.inferred_findings]
        for claim in claims:
            if not set(claim.evidence_ids).issubset(allowed_evidence_ids):
                raise ValueError("Analysis narrative cited unknown evidence")

    @staticmethod
    def _render_analysis_narrative(narrative: AnalysisNarrative) -> str:
        lines = [f"Summary: {narrative.executive_summary}"]
        sections = (
            ("Confirmed", narrative.confirmed_findings),
            ("Inferred", narrative.inferred_findings),
        )
        for heading, claims in sections:
            if claims:
                lines.append(f"\n{heading}:")
                lines.extend(
                    f"- {claim.text} [Evidence: {', '.join(claim.evidence_ids)}]"
                    for claim in claims
                )
        for heading, values in (
            ("Unknown", narrative.unknowns),
            ("Next actions", narrative.next_actions),
            ("Limitations", narrative.limitations),
        ):
            if values:
                lines.append(f"\n{heading}:")
                lines.extend(f"- {value}" for value in values)
        return "\n".join(lines)
