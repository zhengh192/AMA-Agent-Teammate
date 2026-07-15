from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse

from ama_teammate.api.dependencies import (
    DevelopmentUser,
    get_analysis_service,
    get_connector_registry,
    get_current_user,
    get_phase_two_chat_service,
    get_repository,
)
from ama_teammate.api.routes_sessions import require_session
from ama_teammate.api.schemas import ApprovalActionRequest
from ama_teammate.errors import AppError

router = APIRouter(tags=["analysis"])


@router.get("/data-sources")
async def list_data_sources(
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[dict[str, object]]:
    del user
    registry = get_connector_registry(request)
    health = {item.source_id: item for item in await registry.health_checks()}
    return [
        {
            **item,
            "health": health[str(item["id"])].model_dump(),
        }
        for item in registry.redacted_catalog()
    ]


@router.post("/runs/{run_id}/approval/stream")
async def decide_analysis_approval(
    run_id: str,
    payload: ApprovalActionRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> StreamingResponse:
    repository = get_repository(request)
    run = await repository.get_run(run_id)
    if run is None:
        raise AppError(
            status_code=404, code="run_not_found", category="user_input", message="Run not found."
        )
    await require_session(repository, run.session_id, user.id)
    if run.status not in {"waiting_approval", "completed", "cancelled"}:
        raise AppError(
            status_code=409,
            code="run_not_waiting_for_approval",
            category="validation",
            message="This run is not waiting for SQL approval.",
        )
    generator = get_phase_two_chat_service(request).resume_approval_stream(
        run_id, user.id, payload.model_dump()
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/analysis")
async def get_analysis_result(
    run_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, object]:
    repository = get_repository(request)
    run = await repository.get_run(run_id)
    if run is None:
        raise AppError(
            status_code=404, code="run_not_found", category="user_input", message="Run not found."
        )
    await require_session(repository, run.session_id, user.id)
    result = await get_analysis_service(request).result_for_run(run_id)
    if result is None:
        raise AppError(
            status_code=404,
            code="analysis_result_not_found",
            category="user_input",
            message="Analysis result not found.",
        )
    return result.model_dump(mode="json")


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> FileResponse:
    service = get_analysis_service(request)
    artifact = await service.analysis_repository.get_artifact(artifact_id)
    if artifact is None or artifact.run_id is None or artifact.artifact_type != "bounded_csv":
        raise AppError(
            status_code=404,
            code="artifact_not_found",
            category="user_input",
            message="Artifact not found.",
        )
    run = await get_repository(request).get_run(artifact.run_id)
    if run is None:
        raise AppError(
            status_code=404, code="run_not_found", category="user_input", message="Run not found."
        )
    await require_session(get_repository(request), run.session_id, user.id)
    path = Path(artifact.storage_ref).resolve()  # noqa: ASYNC240
    root = service.json_store.root.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError(
            status_code=404,
            code="artifact_not_found",
            category="user_input",
            message="Artifact not found.",
        )
    return FileResponse(
        path,
        media_type="text/csv",
        filename=f"analysis-{run.id}.csv",
    )
