from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime]


class ChatSessionRow(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class DeletedChatSessionRow(Base):
    __tablename__ = "deleted_chat_sessions"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id"), primary_key=True
    )
    deleted_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    deleted_at: Mapped[datetime]


class MessageRow(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    epistemic_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime]


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    route: Mapped[str] = mapped_column(String(32), default="chat")
    provider: Mapped[str] = mapped_column(String(32))
    model_profile: Mapped[str] = mapped_column(String(64), default="coordinator")
    request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class GraphCheckpointRefRow(Base):
    __tablename__ = "graph_checkpoint_refs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), unique=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    store_key: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime]


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    safe_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(128))
    policy_version: Mapped[str] = mapped_column(String(64))
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    graph_node: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    safe_details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime]


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    storage_ref: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(128))
    classification: Mapped[str] = mapped_column(String(32), default="internal")
    status: Mapped[str] = mapped_column(String(32), default="placeholder")
    created_at: Mapped[datetime]


Index("ix_messages_session_created", MessageRow.session_id, MessageRow.created_at)
Index("ix_audit_run_created", AuditEventRow.run_id, AuditEventRow.created_at)
