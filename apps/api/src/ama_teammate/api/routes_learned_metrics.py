from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ama_teammate.api.dependencies import (
    DevelopmentUser,
    get_analysis_service,
    get_current_user,
)
from ama_teammate.errors import AppError

router = APIRouter(prefix="/learned-metrics", tags=["learned-metrics"])


@router.get("")
async def list_learned_metrics(
    request: Request,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[dict[str, object]]:
    service = get_analysis_service(request)
    definitions = (
        await service.search_learned_metrics(user.id, q)
        if q
        else await service.list_learned_metrics(user.id)
    )
    return [item.model_dump(mode="json") for item in definitions]


@router.get("/{definition_id}")
async def get_learned_metric(
    definition_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, object]:
    definition = await get_analysis_service(request).get_learned_metric(
        user.id, definition_id
    )
    if definition is None:
        raise AppError(
            status_code=404,
            code="learned_metric_not_found",
            category="user_input",
            message="Learned metric not found.",
        )
    return definition.model_dump(mode="json")