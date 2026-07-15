from __future__ import annotations

from ama_teammate.config import Settings
from ama_teammate.providers.embeddings import AzureEmbeddingProvider, create_embedding_provider


async def test_mock_embedding_provider_is_deterministic_and_default() -> None:
    settings = Settings(_env_file=None)
    provider = create_embedding_provider(settings)
    first = await provider.embed(["conversion metric"])
    second = await provider.embed(["conversion metric"])
    assert provider.name == "mock"
    assert first == second
    assert (await provider.smoke_test())["ok"] is True


async def test_azure_embedding_smoke_failure_is_sanitized() -> None:
    settings = Settings(_env_file=None, ama_embedding_provider="azure")
    provider = AzureEmbeddingProvider(settings)
    result = await provider.smoke_test()
    assert result["ok"] is False
    assert result["provider"] == "azure"
    assert "AZURE_OPENAI" not in str(result)
    assert "Check approved configuration" in str(result["safe_message"])
