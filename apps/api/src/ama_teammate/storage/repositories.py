from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import select

from ama_teammate.domain.models import MessageRole, RunStatus, new_id, utc_now
from ama_teammate.storage.database import Database
from ama_teammate.storage.schema import (
    AgentRunRow,
    AuditEventRow,
    ChatSessionRow,
    GraphCheckpointRefRow,
    MessageRow,
    UserRow,
)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def ensure_user(self, user_id: str, display_name: str) -> UserRow:
        async with self.database.sessions() as session:
            row = await session.get(UserRow, user_id)
            if row is None:
                row = UserRow(
                    id=user_id,
                    display_name=display_name,
                    status="active",
                    created_at=utc_now(),
                )
                session.add(row)
                await session.commit()
            return row

    async def create_chat_session(self, user_id: str, title: str) -> ChatSessionRow:
        now = utc_now()
        row = ChatSessionRow(
            id=new_id(),
            user_id=user_id,
            title=title.strip() or "New chat",
            created_at=now,
            updated_at=now,
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def list_chat_sessions(self, user_id: str) -> Sequence[ChatSessionRow]:
        async with self.database.sessions() as session:
            result = await session.scalars(
                select(ChatSessionRow)
                .where(ChatSessionRow.user_id == user_id)
                .order_by(ChatSessionRow.updated_at.desc())
            )
            return result.all()

    async def get_chat_session(self, session_id: str, user_id: str) -> ChatSessionRow | None:
        async with self.database.sessions() as session:
            return cast(
                ChatSessionRow | None,
                await session.scalar(
                    select(ChatSessionRow).where(
                        ChatSessionRow.id == session_id, ChatSessionRow.user_id == user_id
                    )
                ),
            )

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        *,
        run_id: str | None = None,
        epistemic_label: str | None = None,
    ) -> MessageRow:
        now = utc_now()
        row = MessageRow(
            id=new_id(),
            session_id=session_id,
            run_id=run_id,
            role=role.value,
            content=content,
            epistemic_label=epistemic_label,
            created_at=now,
        )
        async with self.database.sessions() as session:
            session.add(row)
            chat = await session.get(ChatSessionRow, session_id)
            if chat is not None:
                chat.updated_at = now
            await session.commit()
            return row

    async def list_messages(self, session_id: str) -> Sequence[MessageRow]:
        async with self.database.sessions() as session:
            result = await session.scalars(
                select(MessageRow)
                .where(MessageRow.session_id == session_id)
                .order_by(MessageRow.created_at.asc())
            )
            return result.all()

    async def create_run(self, session_id: str, provider: str) -> AgentRunRow:
        now = utc_now()
        run_id = new_id()
        row = AgentRunRow(
            id=run_id,
            session_id=session_id,
            thread_id=run_id,
            status=RunStatus.CREATED.value,
            route="chat",
            provider=provider,
            model_profile="coordinator",
            created_at=now,
            updated_at=now,
        )
        checkpoint = GraphCheckpointRefRow(
            id=new_id(),
            run_id=run_id,
            thread_id=run_id,
            store_key=f"thread:{run_id}",
            created_at=now,
        )
        async with self.database.sessions() as session:
            session.add_all([row, checkpoint])
            await session.commit()
            return row

    async def get_run(self, run_id: str) -> AgentRunRow | None:
        async with self.database.sessions() as session:
            return await session.get(AgentRunRow, run_id)

    async def update_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        route: str | None = None,
        request_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self.database.sessions() as session:
            row = await session.get(AgentRunRow, run_id)
            if row is None:
                return
            row.status = status.value
            row.updated_at = utc_now()
            if status in {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                row.completed_at = row.updated_at
            if route is not None:
                row.route = route
            if request_id is not None:
                row.request_id = request_id
            if input_tokens is not None:
                row.input_tokens = input_tokens
            if output_tokens is not None:
                row.output_tokens = output_tokens
            if error_code is not None:
                row.error_code = error_code
            await session.commit()

    async def add_audit_event(
        self,
        *,
        actor_id: str,
        event_type: str,
        status: str,
        session_id: str | None = None,
        run_id: str | None = None,
        graph_node: str | None = None,
        input_text: str | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> AuditEventRow:
        row = AuditEventRow(
            id=new_id(),
            session_id=session_id,
            run_id=run_id,
            actor_id=actor_id,
            event_type=event_type,
            graph_node=graph_node,
            status=status,
            input_hash=hash_text(input_text) if input_text else None,
            safe_details_json=json.dumps(safe_details or {}, separators=(",", ":"), sort_keys=True),
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def list_run_audit_events(self, run_id: str) -> Sequence[AuditEventRow]:
        async with self.database.sessions() as session:
            result = await session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.run_id == run_id)
                .order_by(AuditEventRow.created_at.asc())
            )
            return result.all()
