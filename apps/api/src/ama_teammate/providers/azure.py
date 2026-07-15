from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import BaseModel

from ama_teammate.config import Settings
from ama_teammate.domain.models import ProviderEvent, ProviderUsage
from ama_teammate.providers.base import (
    ModelProfile,
    ProviderMessage,
    SmokeTestResult,
    StructuredProviderRequest,
)


class AzureOpenAIProvider:
    """Official OpenAI SDK adapter configured for an Azure OpenAI deployment."""

    name = "azure"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._credential: Any | None = None

    def _build_client(self) -> Any:
        if self._client is not None:
            return self._client
        errors = self.settings.azure_validation_errors()
        if errors:
            raise ValueError("; ".join(errors))

        # SDK and credential imports are deliberately isolated to the provider layer.
        from openai import AsyncAzureOpenAI

        kwargs: dict[str, Any] = {
            "azure_endpoint": self.settings.azure_openai_endpoint,
            "api_version": self.settings.azure_openai_api_version,
            "timeout": self.settings.azure_openai_timeout_seconds,
            "max_retries": self.settings.azure_openai_max_retries,
        }
        if self.settings.azure_openai_auth_mode == "api_key":
            api_key = self.settings.azure_openai_api_key
            if api_key is None:
                raise ValueError("AZURE_OPENAI_API_KEY is required for api_key auth")
            kwargs["api_key"] = api_key.get_secret_value()
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            self._credential = DefaultAzureCredential()
            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                self._credential, self.settings.azure_openai_token_scope
            )
        self._client = AsyncAzureOpenAI(**kwargs)
        return self._client

    async def generate_structured(
        self,
        messages: Sequence[ProviderMessage],
        profile: ModelProfile,
        request: StructuredProviderRequest,
    ) -> BaseModel:
        client = self._build_client()
        api_input = [{"role": message.role, "content": message.content} for message in messages]
        response = await client.responses.parse(
            model=profile.deployment,
            input=api_input,
            text_format=request.schema,
        )
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, request.schema):
            raise ValueError("Azure structured response failed schema validation")
        return parsed

    async def stream(
        self, messages: Sequence[ProviderMessage], profile: ModelProfile
    ) -> AsyncIterator[ProviderEvent]:
        client = self._build_client()
        api_input = [{"role": message.role, "content": message.content} for message in messages]
        stream = await client.responses.create(
            model=profile.deployment,
            input=api_input,
            stream=True,
        )
        async for event in stream:
            event_type = str(getattr(event, "type", "unknown"))
            if event_type == "response.output_text.delta":
                yield ProviderEvent(event_type=event_type, delta=str(getattr(event, "delta", "")))
            elif event_type == "response.completed":
                response = getattr(event, "response", None)
                usage_value = getattr(response, "usage", None)
                usage = ProviderUsage(
                    input_tokens=int(getattr(usage_value, "input_tokens", 0) or 0),
                    output_tokens=int(getattr(usage_value, "output_tokens", 0) or 0),
                    total_tokens=int(getattr(usage_value, "total_tokens", 0) or 0),
                )
                yield ProviderEvent(
                    event_type=event_type,
                    request_id=getattr(response, "_request_id", None),
                    usage=usage,
                )

    async def smoke_test(self, profile: ModelProfile) -> SmokeTestResult:
        try:
            client = self._build_client()
            response = await client.responses.create(
                model=profile.deployment,
                input="Reply with exactly OK.",
                max_output_tokens=64,
            )
            return SmokeTestResult(
                ok=True,
                provider=self.name,
                deployment=profile.deployment,
                request_id=getattr(response, "_request_id", None),
                safe_message="Azure OpenAI responded successfully.",
            )
        except Exception as exc:
            return SmokeTestResult(
                ok=False,
                provider=self.name,
                deployment=profile.deployment,
                error_code=type(exc).__name__,
                safe_message="Azure OpenAI connection failed. Check approved endpoint, deployment, auth, and API version.",
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._credential is not None:
            close = getattr(self._credential, "close", None)
            if close is not None:
                close()
