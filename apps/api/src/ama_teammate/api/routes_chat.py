from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ama_teammate.api.dependencies import (
    DevelopmentUser,
    get_chat_service,
    get_current_user,
    get_repository,
)
from ama_teammate.api.routes_sessions import require_session
from ama_teammate.api.schemas import MessageRequest, TraceEventResponse
from ama_teammate.errors import AppError

router = APIRouter(tags=["chat"])


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    payload: MessageRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> StreamingResponse:
    repository = get_repository(request)
    await require_session(repository, session_id, user.id)
    generator = get_chat_service(request).start_stream(session_id, user.id, payload.content)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/resume/stream")
async def resume_run(
    run_id: str,
    payload: MessageRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> StreamingResponse:
    repository = get_repository(request)
    run = await repository.get_run(run_id)
    if run is None:
        raise AppError(
            status_code=404,
            code="run_not_found",
            category="user_input",
            message="Run not found.",
        )
    await require_session(repository, run.session_id, user.id)
    if run.status != "clarifying":
        raise AppError(
            status_code=409,
            code="run_not_waiting_for_clarification",
            category="validation",
            message="This run is not waiting for clarification.",
        )
    generator = get_chat_service(request).resume_stream(run_id, user.id, payload.content)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/trace", response_model=list[TraceEventResponse])
async def get_trace(
    run_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[TraceEventResponse]:
    repository = get_repository(request)
    run = await repository.get_run(run_id)
    if run is None:
        raise AppError(
            status_code=404, code="run_not_found", category="user_input", message="Run not found."
        )
    await require_session(repository, run.session_id, user.id)
    rows = await repository.list_run_audit_events(run_id)
    return [
        TraceEventResponse(
            id=row.id,
            event_type=row.event_type,
            graph_node=row.graph_node,
            status=row.status,
            safe_details=json.loads(row.safe_details_json),
            created_at=row.created_at,
        )
        for row in rows
    ]
