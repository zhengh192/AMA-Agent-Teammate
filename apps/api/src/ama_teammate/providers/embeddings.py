from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Any, Protocol

from ama_teammate.config import Settings


class EmbeddingProvider(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def smoke_test(self) -> dict[str, str | bool]: ...

    async def close(self) -> None: ...


class MockEmbeddingProvider:
    name = "mock"

    def __init__(self, dimensions: int = 96) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in _tokens(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                vector[index] += -1.0 if digest[4] & 1 else 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    async def smoke_test(self) -> dict[str, str | bool]:
        return {"ok": True, "provider": self.name, "safe_message": "Mock embeddings ready."}

    async def close(self) -> None:
        return None


class AzureEmbeddingProvider:
    """Azure OpenAI embedding adapter; SDK objects never cross this boundary."""

    name = "azure"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._credential: Any | None = None

    def _build_client(self) -> Any:
        if self._client is not None:
            return self._client
        errors = self.settings.azure_embedding_validation_errors()
        if errors:
            raise ValueError("; ".join(errors))
        from openai import AsyncAzureOpenAI

        kwargs: dict[str, Any] = {
            "azure_endpoint": self.settings.azure_openai_endpoint,
            "api_version": self.settings.azure_openai_api_version,
            "timeout": self.settings.azure_openai_timeout_seconds,
            "max_retries": self.settings.azure_openai_max_retries,
        }
        if self.settings.azure_openai_auth_mode == "api_key":
            key = self.settings.azure_openai_api_key
            if key is None:
                raise ValueError("AZURE_OPENAI_API_KEY is required for api_key auth")
            kwargs["api_key"] = key.get_secret_value()
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            self._credential = DefaultAzureCredential()
            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                self._credential, self.settings.azure_openai_token_scope
            )
        self._client = AsyncAzureOpenAI(**kwargs)
        return self._client

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        deployment = self.settings.azure_openai_embedding_deployment
        if deployment is None:
            raise ValueError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is required")
        response = await self._build_client().embeddings.create(
            model=deployment, input=list(texts), encoding_format="float"
        )
        ordered = sorted(response.data, key=lambda item: int(item.index))
        return [list(map(float, item.embedding)) for item in ordered]

    async def smoke_test(self) -> dict[str, str | bool]:
        try:
            await self.embed(["connection test"])
            return {
                "ok": True,
                "provider": self.name,
                "deployment": self.settings.azure_openai_embedding_deployment or "unconfigured",
                "safe_message": "Azure embeddings responded successfully.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.name,
                "error_code": type(exc).__name__,
                "safe_message": "Azure embedding connection failed. Check approved configuration.",
            }

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._credential is not None:
            close = getattr(self._credential, "close", None)
            if close is not None:
                close()


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.ama_embedding_provider == "azure":
        return AzureEmbeddingProvider(settings)
    return MockEmbeddingProvider()


def _tokens(text: str) -> list[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in text)
    words = normalized.split()
    cjk = [character for character in text if "\u4e00" <= character <= "\u9fff"]
    return words + cjk
