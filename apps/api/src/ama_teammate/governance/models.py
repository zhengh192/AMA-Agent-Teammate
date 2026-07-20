from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceLocation(BaseModel):
    page: int | None = None
    sheet: str | None = None
    section: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None

    def label(self) -> str:
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"page {self.page}")
        if self.sheet:
            parts.append(f"sheet {self.sheet}")
        if self.section:
            parts.append(f"section {self.section}")
        if self.row_start is not None:
            end = self.row_end or self.row_start
            parts.append(f"rows {self.row_start}-{end}")
        if self.line_start is not None:
            end = self.line_end or self.line_start
            parts.append(f"lines {self.line_start}-{end}")
        return ", ".join(parts) or "document"


class ParsedChunk(BaseModel):
    content: str
    location: SourceLocation


class DocumentView(BaseModel):
    id: str
    filename: str
    media_type: str
    status: str
    version: int
    content_hash: str
    scan_status: str
    parser_status: str
    error_code: str | None = None
    chunks: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Citation(BaseModel):
    document_id: str
    document_version_id: str
    chunk_id: str
    filename: str
    version: int
    location: SourceLocation
    excerpt: str
    score: float


class KnowledgeAnswer(BaseModel):
    answer: str
    epistemic_label: Literal["Confirmed", "Unknown", "Need confirmation"]
    citations: list[Citation] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class SkillProposalRequest(BaseModel):
    teaching: str = Field(min_length=10, max_length=10_000)
    owner: str | None = None


class AnalysisSkillProposalRequest(BaseModel):
    metadata: dict[str, Any]
    instructions: str = Field(min_length=20, max_length=50_000)


class SkillRevisionRequest(BaseModel):
    instructions: str = Field(min_length=20, max_length=50_000)


class KnowledgeEntryRequest(BaseModel):
    kind: Literal[
        "business_context",
        "metric",
        "data_source",
        "table",
        "field",
        "business_rule",
        "process",
    ]
    name: str = Field(min_length=2, max_length=240)
    definition: str = Field(min_length=5, max_length=20_000)
    owner: str = Field(min_length=2, max_length=200)
    source: str = Field(min_length=2, max_length=500)
    effective_date: str | None = Field(default=None, max_length=40)


class ProposalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    payload_hash: str
    comment: str | None = Field(default=None, max_length=500)


class MemoryProposalRequest(BaseModel):
    scope: Literal["session", "project", "user_preference", "entity"]
    key: str = Field(min_length=1, max_length=160)
    value: dict[str, Any]
    source: str = Field(min_length=1, max_length=240)
    expires_at: datetime | None = None


class MemoryEditRequest(BaseModel):
    value: dict[str, Any]
    source: str = Field(min_length=1, max_length=240)
    expires_at: datetime | None = None
