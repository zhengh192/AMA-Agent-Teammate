from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from ama_teammate.config import Settings
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.providers.factory import ProviderBundle
from ama_teammate.services.analysis import AnalysisService
from ama_teammate.services.chat import ChatService
from ama_teammate.services.phase2_chat import PhaseTwoChatService
from ama_teammate.storage.repositories import Repository


@dataclass(frozen=True, slots=True)
class DevelopmentUser:
    id: str
    display_name: str


def get_settings_from_app(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def get_chat_service(request: Request) -> ChatService:
    return cast(ChatService, request.app.state.chat_service)


def get_phase_two_chat_service(request: Request) -> PhaseTwoChatService:
    return cast(PhaseTwoChatService, request.app.state.chat_service)


def get_analysis_service(request: Request) -> AnalysisService:
    return cast(AnalysisService, request.app.state.analysis_service)


def get_connector_registry(request: Request) -> ConnectorRegistry:
    return cast(ConnectorRegistry, request.app.state.connector_registry)


def get_provider_bundle(request: Request) -> ProviderBundle:
    return cast(ProviderBundle, request.app.state.providers)


def get_current_user(request: Request) -> DevelopmentUser:
    settings = get_settings_from_app(request)
    return DevelopmentUser(
        id=settings.ama_development_user_id,
        display_name=settings.ama_development_user_name,
    )
