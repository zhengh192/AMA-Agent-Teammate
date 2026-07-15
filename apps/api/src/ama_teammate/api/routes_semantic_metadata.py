from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from ama_teammate.api.dependencies import DevelopmentUser, get_current_user
from ama_teammate.errors import AppError
from ama_teammate.semantic_metadata.models import DefinitionStatus, DefinitionType
from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry

router = APIRouter(prefix="/semantic-metadata", tags=["semantic-metadata"])


def _registry(request: Request) -> SemanticMetadataRegistry:
    return request.app.state.semantic_metadata_registry  # type: ignore[no-any-return]


def _response(item: Any) -> dict[str, Any]:
    result = item.model_dump(mode="json")
    result["definition_type"] = item.kind
    return result  # type: ignore[no-any-return]


@router.get("")
async def list_definitions(
    request: Request,
    definition_type: DefinitionType | None = None,
    status: DefinitionStatus | None = None,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    del user
    return [_response(item) for item in _registry(request).list_definitions(definition_type, status)]


@router.get("/search")
async def search_definitions(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    definition_type: DefinitionType | None = None,
    status: DefinitionStatus | None = None,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    del user
    return [
        _response(item)
        for item in _registry(request).search(q, definition_type=definition_type, status=status)
    ]


@router.get("/{definition_type}/{definition_id}")
async def get_definition(
    definition_type: DefinitionType,
    definition_id: str,
    request: Request,
    version: str | None = None,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    del user
    try:
        return _response(_registry(request).get(definition_type, definition_id, version))
    except LookupError as exc:
        raise AppError(
            status_code=404,
            code="semantic_definition_not_found",
            category="user_input",
            message=str(exc),
        ) from exc
