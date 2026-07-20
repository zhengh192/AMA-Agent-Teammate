from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ama_teammate.api.dependencies import DevelopmentUser, get_current_user, get_repository
from ama_teammate.api.schemas import (
    CreateSessionRequest,
    MessageResponse,
    SessionResponse,
)
from ama_teammate.errors import AppError
from ama_teammate.storage.repositories import Repository

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> SessionResponse:
    repository = get_repository(request)
    row = await repository.create_chat_session(user.id, payload.title)
    await repository.add_audit_event(
        actor_id=user.id,
        event_type="session.created",
        status="success",
        session_id=row.id,
        safe_details={"title_length": len(row.title)},
    )
    return SessionResponse.model_validate(row)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[SessionResponse]:
    rows = await get_repository(request).list_chat_sessions(user.id)
    return [SessionResponse.model_validate(row) for row in rows]


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> Response:
    repository = get_repository(request)
    if not await repository.delete_chat_session(session_id, user.id):
        raise AppError(
            status_code=404,
            code="session_not_found",
            category="permission",
            message="Session not found.",
            recovery="Select a session you own.",
        )
    await repository.add_audit_event(
        actor_id=user.id,
        event_type="session.deleted",
        status="success",
        session_id=session_id,
        safe_details={"deletion_mode": "logical"},
    )
    return Response(status_code=204)

async def require_session(repository: Repository, session_id: str, user_id: str) -> None:
    if await repository.get_chat_session(session_id, user_id) is None:
        raise AppError(
            status_code=404,
            code="session_not_found",
            category="permission",
            message="Session not found.",
            recovery="Create a session or select one you own.",
        )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> list[MessageResponse]:
    repository = get_repository(request)
    await require_session(repository, session_id, user.id)
    rows = await repository.list_messages(session_id)
    return [MessageResponse.model_validate(row) for row in rows]
