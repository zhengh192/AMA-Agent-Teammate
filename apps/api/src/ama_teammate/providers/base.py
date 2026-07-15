from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from ama_teammate.domain.models import ProviderEvent


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class StructuredProviderRequest:
    name: str
    schema: type[BaseModel]


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    deployment: str


@dataclass(frozen=True, slots=True)
class SmokeTestResult:
    ok: bool
    provider: str
    deployment: str
    request_id: str | None = None
    error_code: str | None = None
    safe_message: str | None = None


class LLMProvider(Protocol):
    name: str

    async def generate_structured(
        self,
        messages: Sequence[ProviderMessage],
        profile: ModelProfile,
        request: StructuredProviderRequest,
    ) -> BaseModel: ...

    def stream(
        self, messages: Sequence[ProviderMessage], profile: ModelProfile
    ) -> AsyncIterator[ProviderEvent]: ...

    async def smoke_test(self, profile: ModelProfile) -> SmokeTestResult: ...

    async def close(self) -> None: ...
