from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    CREATED = "created"
    CLARIFYING = "clarifying"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EpistemicLabel(StrEnum):
    CONFIRMED = "Confirmed"
    INFERRED = "Inferred"
    UNKNOWN = "Unknown"
    NEED_CONFIRMATION = "Need confirmation"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ProviderUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ProviderEvent(BaseModel):
    event_type: str
    delta: str = ""
    request_id: str | None = None
    usage: ProviderUsage | None = None


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)


class StructuredError(BaseModel):
    code: str
    category: str
    message: str
    recovery: str | None = None
    correlation_id: str | None = None


class ApprovalDecision(BaseModel):
    approval_id: str
    status: ApprovalStatus
    comment: str | None = None
