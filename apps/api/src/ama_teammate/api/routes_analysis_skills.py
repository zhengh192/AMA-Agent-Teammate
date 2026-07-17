from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from ama_teammate.analysis_skills.models import SkillStatus
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry
from ama_teammate.errors import AppError

router = APIRouter(prefix="/analysis-skills", tags=["analysis-skills"])


def _registry(request: Request) -> AnalysisSkillRegistry:
    return request.app.state.analysis_skill_registry  # type: ignore[no-any-return]


def _view(package: object, *, include_instructions: bool = False) -> dict[str, object]:
    from ama_teammate.analysis_skills.models import SkillPackage

    assert isinstance(package, SkillPackage)
    value: dict[str, object] = package.metadata.model_dump(mode="json")
    value["path"] = package.path
    if include_instructions:
        value["instructions"] = package.instructions
    return value


@router.get("")
async def list_analysis_skills(
    request: Request, status: Annotated[SkillStatus | None, Query()] = None
) -> list[dict[str, object]]:
    return [_view(item) for item in _registry(request).list_packages(status)]


@router.get("/search")
async def search_analysis_skills(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    status: Annotated[SkillStatus | None, Query()] = SkillStatus.ACTIVE,
) -> list[dict[str, object]]:
    return [_view(item) for item in _registry(request).search(q, status)]


@router.get("/{skill_id}")
async def get_analysis_skill(
    skill_id: str, request: Request, version: Annotated[str | None, Query()] = None
) -> dict[str, object]:
    try:
        return _view(_registry(request).get(skill_id, version), include_instructions=True)
    except LookupError as exc:
        raise AppError(
            status_code=404,
            code="analysis_skill_not_found",
            category="user_input",
            message="Analysis skill not found.",
        ) from exc
