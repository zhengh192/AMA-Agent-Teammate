from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from pydantic import BaseModel

from ama_teammate.domain.models import ProviderEvent, ProviderUsage
from ama_teammate.providers.base import (
    ModelProfile,
    ProviderMessage,
    SmokeTestResult,
    StructuredProviderRequest,
)
from ama_teammate.providers.structured_mock import (
    analysis_intent_fixture,
    analysis_narrative_fixture,
    goal_assessment_fixture,
)


class MockLLMProvider:
    name = "mock"

    async def generate_structured(
        self,
        messages: Sequence[ProviderMessage],
        profile: ModelProfile,
        request: StructuredProviderRequest,
    ) -> BaseModel:
        del profile
        user_text = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        fixtures = {
            "analysis_intent": analysis_intent_fixture,
            "analysis_narrative": analysis_narrative_fixture,
            "goal_assessment": goal_assessment_fixture,
        }
        if request.name not in fixtures:
            raise ValueError(f"Unknown mock structured fixture: {request.name}")
        return request.schema.model_validate(fixtures[request.name](user_text))

    async def stream(
        self, messages: Sequence[ProviderMessage], profile: ModelProfile
    ) -> AsyncIterator[ProviderEvent]:
        user_text = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        current_text = user_text.rsplit("<current_request>", 1)[-1].split("</current_request>", 1)[
            0
        ]
        lower = current_text.lower()
        analysis_markers: tuple[str, ...]
        knowledge_markers: tuple[str, ...]
        analysis_markers = ("data", "database", "query", "sql", "metric", "分析", "数据", "查询")
        knowledge_markers = ("document", "knowledge", "upload", "文档", "知识", "上传")
        analysis_markers += ("\u5206\u6790", "\u6570\u636e", "\u67e5\u8be2")
        knowledge_markers += ("\u6587\u6863", "\u77e5\u8bc6", "\u4e0a\u4f20")
        if any(marker in lower for marker in analysis_markers):
            text = (
                "Unknown: no approved analysis result was supplied to this response path. "
                "Need confirmation: provide the material metric and time range if they are absent; "
                "no database query is claimed here."
            )
        elif any(marker in lower for marker in knowledge_markers):
            text = (
                "Unknown: no approved cited knowledge excerpt was supplied to this response path. "
                "No document content is claimed here."
            )
        else:
            text = (
                "Confirmed: the Agent chat foundation is running with the Mock Provider. "
                f"I received your message: {user_text.strip()}"
            )

        for index in range(0, len(text), 18):
            await asyncio.sleep(0)
            yield ProviderEvent(
                event_type="response.output_text.delta", delta=text[index : index + 18]
            )
        input_tokens = max(1, sum(len(message.content) for message in messages) // 4)
        output_tokens = max(1, len(text) // 4)
        yield ProviderEvent(
            event_type="response.completed",
            request_id="mock-request",
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def smoke_test(self, profile: ModelProfile) -> SmokeTestResult:
        return SmokeTestResult(ok=True, provider=self.name, deployment=profile.deployment)

    async def close(self) -> None:
        return None
