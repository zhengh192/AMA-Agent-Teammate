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
from ama_teammate.providers.structured_mock import analysis_intent_fixture


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
        if request.name != "analysis_intent":
            raise ValueError(f"Unknown mock structured fixture: {request.name}")
        return request.schema.model_validate(analysis_intent_fixture(user_text))

    async def stream(
        self, messages: Sequence[ProviderMessage], profile: ModelProfile
    ) -> AsyncIterator[ProviderEvent]:
        user_text = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        lower = user_text.lower()
        analysis_markers = ("data", "database", "query", "sql", "metric", "分析", "数据", "查询")
        knowledge_markers = ("document", "knowledge", "upload", "文档", "知识", "上传")
        if any(marker in lower for marker in analysis_markers):
            text = (
                "Unknown: Phase 1 has no database connectors and no query was executed. "
                "Need confirmation: provide the intended metric, time range, and approved data source; "
                "database analysis is intentionally postponed to Phase 2."
            )
        elif any(marker in lower for marker in knowledge_markers):
            text = (
                "Unknown: Phase 1 has no document retrieval pipeline and no file content was read. "
                "Need confirmation: document ingestion and cited retrieval are intentionally postponed to Phase 3."
            )
        else:
            text = (
                "Confirmed: the Phase 1 chat foundation is running with the Mock Provider. "
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
