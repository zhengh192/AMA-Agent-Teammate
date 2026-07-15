from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    title: str = Field(default="New chat", max_length=240)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class ApprovalActionRequest(BaseModel):
    approval_id: str = Field(min_length=1, max_length=64)
    payload_hash: str = Field(min_length=64, max_length=128)
    status: str = Field(pattern="^(approved|rejected|changes_requested)$")
    comment: str | None = Field(default=None, max_length=2_000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    run_id: str | None
    role: str
    content: str
    epistemic_label: str | None
    created_at: datetime


class TraceEventResponse(BaseModel):
    id: str
    event_type: str
    graph_node: str | None
    status: str
    safe_details: dict[str, Any]
    created_at: datetime


class ProviderSmokeResponse(BaseModel):
    ok: bool
    provider: str
    deployment: str
    request_id: str | None = None
    error_code: str | None = None
    safe_message: str | None = None
