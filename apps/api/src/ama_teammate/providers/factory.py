from __future__ import annotations

from dataclasses import dataclass

from ama_teammate.config import Settings
from ama_teammate.providers.azure import AzureOpenAIProvider
from ama_teammate.providers.base import LLMProvider, ModelProfile
from ama_teammate.providers.mock import MockLLMProvider


@dataclass(slots=True)
class ProviderBundle:
    provider: LLMProvider
    coordinator: ModelProfile
    analyst: ModelProfile
    curator: ModelProfile


def create_provider_bundle(settings: Settings) -> ProviderBundle:
    if settings.ama_provider == "azure":
        provider: LLMProvider = AzureOpenAIProvider(settings)
        coordinator_deployment = settings.azure_openai_deployment_coordinator or "unconfigured"
        analyst_deployment = settings.azure_openai_deployment_analyst or coordinator_deployment
        curator_deployment = settings.azure_openai_deployment_curator or coordinator_deployment
    else:
        provider = MockLLMProvider()
        coordinator_deployment = "mock-coordinator"
        analyst_deployment = "mock-analyst"
        curator_deployment = "mock-curator"
    return ProviderBundle(
        provider=provider,
        coordinator=ModelProfile(name="coordinator", deployment=coordinator_deployment),
        analyst=ModelProfile(name="data_analyst", deployment=analyst_deployment),
        curator=ModelProfile(name="knowledge_curator", deployment=curator_deployment),
    )
