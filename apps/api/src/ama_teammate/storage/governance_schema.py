from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ama_teammate.storage.schema import Base


class DocumentRow(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(240))
    media_type: Mapped[str] = mapped_column(String(120))
    classification: Mapped[str] = mapped_column(String(32), default="internal")
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime]


class DocumentVersionRow(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_document_version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    storage_ref: Mapped[str] = mapped_column(String(500))
    source_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    scan_status: Mapped[str] = mapped_column(String(32))
    parser_status: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime]


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    location_json: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128))
    embedding_json: Mapped[str] = mapped_column(Text)
    trust: Mapped[str] = mapped_column(String(32), default="untrusted_source")
    index_status: Mapped[str] = mapped_column(String(32), default="indexed")
    created_at: Mapped[datetime]


class KnowledgeRecordRow(Base):
    __tablename__ = "knowledge_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    definition: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deprecated: Mapped[bool] = mapped_column(default=False)
    source_chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunks.id"))
    created_at: Mapped[datetime]


class KnowledgeConflictRow(Base):
    __tablename__ = "knowledge_conflicts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    left_record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"))
    right_record_id: Mapped[str] = mapped_column(ForeignKey("knowledge_records.id"))
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime]


class KnowledgeProposalRow(Base):
    __tablename__ = "knowledge_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(24))
    target_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    base_version: Mapped[int | None] = mapped_column(nullable=True)
    filename: Mapped[str] = mapped_column(String(240))
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime]
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SkillProposalRow(Base):
    __tablename__ = "skill_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    source_text_hash: Mapped[str] = mapped_column(String(128))
    diff_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(128), unique=True)
    tool_allowlist_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    base_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime]
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SkillVersionRow(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_skill_name_version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    path: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(128))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("skill_proposals.id"))
    rollback_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime]
    deprecated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MemoryProposalRow(Base):
    __tablename__ = "memory_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(32))
    memory_key: Mapped[str] = mapped_column(String(160))
    value_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(240))
    payload_hash: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime]
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MemoryVersionRow(Base):
    __tablename__ = "memory_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(32))
    memory_key: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[int]
    value_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), index=True)
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("memory_proposals.id"))
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
