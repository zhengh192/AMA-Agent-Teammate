from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ama_teammate.domain.models import MessageRole, RunStatus, StreamEvent
from ama_teammate.governance.service import TEACHING_MARKERS, GovernanceService
from ama_teammate.services.chat import encode_sse
from ama_teammate.services.phase2_chat import PhaseTwoChatService


class PhaseThreeChatService(PhaseTwoChatService):
    def __init__(self, *, governance_service: GovernanceService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.governance_service = governance_service

    async def start_stream(self, session_id: str, user_id: str, content: str) -> AsyncIterator[str]:
        lowered = content.lower()
        if any(marker in lowered for marker in TEACHING_MARKERS):
            async for item in self._stream_skill_proposal(session_id, user_id, content):
                yield item
            return
        if any(marker in lowered for marker in ("根据上传", "根据文档", "knowledge:", "document:")):
            async for item in self._stream_knowledge_answer(session_id, user_id, content):
                yield item
            return
        async for item in super().start_stream(session_id, user_id, content):
            yield item

    async def prepare_input(
        self, user_id: str, content: str, run_id: str, session_id: str
    ) -> str:
        skills = await self.governance_service.active_skill_context(user_id)
        lowered = content.lower()
        skills = [
            skill
            for skill in skills
            if (skill["name"] == "conversion-decline-analysis" and "conversion" in lowered)
            or (skill["name"] == "taught-analysis-method" and "analysis" in lowered)
        ]
        if not skills:
            return content
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="skill.invoked",
            status="success",
            session_id=session_id,
            run_id=run_id,
            safe_details={
                "skills": [
                    {"name": skill["name"], "version": skill["version"]} for skill in skills
                ]
            },
        )
        context = "\n\n".join(
            f"Approved Skill {skill['name']} v{skill['version']}:\n{skill['instructions']}"
            for skill in skills
        )
        return f"{content}\n\n<approved_skill_context>\n{context}\n</approved_skill_context>"

    async def _stream_skill_proposal(
        self, session_id: str, user_id: str, content: str
    ) -> AsyncIterator[str]:
        run = await self.repository.create_run(session_id, self.providers.provider.name)
        await self.repository.add_message(session_id, MessageRole.USER, content, run_id=run.id)
        yield encode_sse(
            StreamEvent(event="run.started", data={"run_id": run.id, "status": "planning"})
        )
        proposal = await self.governance_service.propose_skill(user_id, content)
        text = (
            f"Need confirmation: Skill {proposal['name']} v{proposal['version']} was proposed. "
            "It is not active and will not influence execution until the exact diff is approved."
        )
        await self.repository.add_message(
            session_id,
            MessageRole.ASSISTANT,
            text,
            run_id=run.id,
            epistemic_label="Need confirmation",
        )
        await self.repository.update_run(run.id, RunStatus.WAITING_APPROVAL, route="knowledge")
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="skill.approval.required",
            status="waiting",
            session_id=session_id,
            run_id=run.id,
            safe_details={
                "proposal_id": proposal["id"], "payload_hash": proposal["payload_hash"]
            },
        )
        yield encode_sse(StreamEvent(event="skill.proposal", data={"run_id": run.id, **proposal}))
        yield encode_sse(
            StreamEvent(
                event="governance.approval.required", data={"run_id": run.id, **proposal}
            )
        )
        yield encode_sse(StreamEvent(event="message.delta", data={"run_id": run.id, "delta": text}))
        yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run.id}))

    async def _stream_knowledge_answer(
        self, session_id: str, user_id: str, content: str
    ) -> AsyncIterator[str]:
        run = await self.repository.create_run(session_id, self.providers.provider.name)
        await self.repository.add_message(session_id, MessageRole.USER, content, run_id=run.id)
        yield encode_sse(
            StreamEvent(event="run.started", data={"run_id": run.id, "status": "executing"})
        )
        result = await self.governance_service.answer(user_id, content)
        await self.repository.add_message(
            session_id,
            MessageRole.ASSISTANT,
            result.answer,
            run_id=run.id,
            epistemic_label=result.epistemic_label,
        )
        await self.repository.update_run(run.id, RunStatus.COMPLETED, route="knowledge")
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="knowledge.retrieved",
            status="success",
            session_id=session_id,
            run_id=run.id,
            input_text=content,
            safe_details={
                "chunk_ids": [citation.chunk_id for citation in result.citations],
                "epistemic_label": result.epistemic_label,
                "conflict_ids": [str(item["id"]) for item in result.conflicts],
            },
        )
        yield encode_sse(
            StreamEvent(event="message.delta", data={"run_id": run.id, "delta": result.answer})
        )
        yield encode_sse(
            StreamEvent(event="knowledge.answer", data={"run_id": run.id, **result.model_dump(mode="json")})
        )
        yield encode_sse(
            StreamEvent(
                event="run.completed",
                data={
                    "run_id": run.id,
                    "status": "completed",
                    "epistemic_label": result.epistemic_label,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                },
            )
        )
        yield encode_sse(StreamEvent(event="stream.end", data={"run_id": run.id}))
