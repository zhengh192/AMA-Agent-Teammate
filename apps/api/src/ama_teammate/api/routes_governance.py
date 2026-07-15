from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from ama_teammate.api.dependencies import DevelopmentUser, get_current_user
from ama_teammate.errors import AppError
from ama_teammate.governance.models import (
    MemoryEditRequest,
    MemoryProposalRequest,
    ProposalDecision,
    SkillProposalRequest,
)
from ama_teammate.governance.service import GovernanceService

router = APIRouter(tags=["knowledge-governance"])


class KnowledgeQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=5_000)
    limit: int = Field(default=5, ge=1, le=10)


def _service(request: Request) -> GovernanceService:
    return request.app.state.governance_service  # type: ignore[no-any-return]


def _safe_error(exc: Exception) -> AppError:
    if isinstance(exc, LookupError):
        return AppError(
            status_code=404,
            code="governance_record_not_found",
            category="user_input",
            message=str(exc),
        )
    return AppError(
        status_code=400,
        code="governance_validation_failed",
        category="validation",
        message=str(exc),
        recovery="Review the safe validation message and submit a revised request.",
    )


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    classification: Annotated[str, Form()] = "internal",
    owner: Annotated[str | None, Form()] = None,
    effective_date: Annotated[str | None, Form()] = None,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if classification not in {"public", "internal", "confidential"}:
        raise _safe_error(ValueError("Unsupported classification."))
    data = await file.read(_service(request).settings.ama_upload_max_bytes + 1)
    try:
        return await _service(request).ingest(
            owner_id=user.id,
            filename=file.filename or "upload",
            media_type=file.content_type,
            data=data,
            classification=classification,
            source_metadata={
                "owner": owner or user.display_name,
                "effective_date": effective_date,
                "uploader": user.id,
                "classification": classification,
            },
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.get("/documents")
async def list_documents(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return await _service(request).list_documents(user.id)


@router.post("/documents/{document_id}/decision")
async def decide_document(
    document_id: str,
    payload: ProposalDecision,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).decide_document(
            user.id, document_id, payload.payload_hash, payload.decision
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.post("/knowledge/ask")
async def ask_knowledge(
    payload: KnowledgeQuestion,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = await _service(request).answer(user.id, payload.question, payload.limit)
    return result.model_dump(mode="json")


@router.get("/knowledge/conflicts")
async def list_conflicts(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return await _service(request).list_conflicts(user.id)


@router.post("/skills/proposals")
async def propose_skill(
    payload: SkillProposalRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).propose_skill(user.id, payload.teaching)
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.get("/skills/proposals")
async def list_skill_proposals(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return await _service(request).list_skill_proposals(user.id)


@router.post("/skills/proposals/{proposal_id}/decision")
async def decide_skill(
    proposal_id: str,
    payload: ProposalDecision,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).decide_skill(
            user.id, proposal_id, payload.payload_hash, payload.decision
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.post("/skills/{name}/{version}/deprecate")
async def deprecate_skill(
    name: str,
    version: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).deprecate_skill(user.id, name, version)
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.post("/skills/{name}/{version}/rollback")
async def rollback_skill(
    name: str,
    version: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).rollback_skill(user.id, name, version)
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.post("/memories/proposals")
async def propose_memory(
    payload: MemoryProposalRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).propose_memory(
            user.id,
            payload.scope,
            payload.key,
            payload.value,
            payload.source,
            payload.expires_at,
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.get("/memories/proposals")
async def list_memory_proposals(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return await _service(request).list_memory_proposals(user.id)


@router.post("/memories/proposals/{proposal_id}/decision")
async def decide_memory(
    proposal_id: str,
    payload: ProposalDecision,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).decide_memory(
            user.id, proposal_id, payload.payload_hash, payload.decision
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.get("/memories")
async def list_memories(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return await _service(request).list_memories(user.id)


@router.patch("/memories/{memory_id}")
async def edit_memory(
    memory_id: str,
    payload: MemoryEditRequest,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    memories = await _service(request).list_memories(user.id)
    current = next((item for item in memories if item["id"] == memory_id), None)
    if current is None:
        raise _safe_error(LookupError("Memory not found."))
    try:
        return await _service(request).propose_memory(
            user.id,
            str(current["scope"]),
            str(current["key"]),
            payload.value,
            payload.source,
            payload.expires_at,
        )
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(request).delete_memory(user.id, memory_id)
    except Exception as exc:
        raise _safe_error(exc) from exc


@router.get("/providers/embeddings/smoke")
async def embedding_smoke(request: Request) -> dict[str, str | bool]:
    return await _service(request).embeddings.smoke_test()
