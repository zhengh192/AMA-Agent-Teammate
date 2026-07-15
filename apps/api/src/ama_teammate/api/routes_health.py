from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from sqlalchemy import text

from ama_teammate.api.dependencies import get_provider_bundle, get_settings_from_app
from ama_teammate.api.schemas import ProviderSmokeResponse

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, object]:
    database = request.app.state.database
    async with database.sessions() as session:
        await session.execute(text("SELECT 1"))
    settings = get_settings_from_app(request)
    azure_errors = settings.azure_validation_errors() if settings.ama_provider == "azure" else []
    return {
        "status": "ready" if not azure_errors else "not_ready",
        "database": "ok",
        "provider": settings.ama_provider,
        "provider_configuration": "ok" if not azure_errors else "invalid",
        "configuration_errors": azure_errors,
    }


@router.post("/provider/smoke", response_model=ProviderSmokeResponse)
async def provider_smoke(request: Request) -> ProviderSmokeResponse:
    providers = get_provider_bundle(request)
    result = await providers.provider.smoke_test(providers.coordinator)
    return ProviderSmokeResponse(**asdict(result))
