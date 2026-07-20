from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import select

from ama_teammate.domain.models import ApprovalStatus, new_id, utc_now
from ama_teammate.jira.models import JiraActionPlan
from ama_teammate.storage.database import Database
from ama_teammate.storage.jira_schema import JiraActionRow
from ama_teammate.storage.repositories import hash_text
from ama_teammate.storage.schema import ApprovalRow

POLICY_VERSION = "jira-actions-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class JiraActionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_with_approval(
        self, *, run_id: str, requester_id: str, plan: JiraActionPlan
    ) -> tuple[JiraActionRow, ApprovalRow]:
        if not plan.requires_approval:
            raise ValueError("Only Jira writes require persisted approval")
        now = utc_now()
        payload_json = canonical_json(plan.approval_payload())
        payload_hash = hash_text(payload_json)
        action = JiraActionRow(
            id=new_id(),
            run_id=run_id,
            action_type=plan.action,
            payload_json=payload_json,
            payload_hash=payload_hash,
            policy_version=POLICY_VERSION,
            status="waiting_approval",
            result_json=None,
            created_at=now,
            updated_at=now,
        )
        approval = ApprovalRow(
            id=new_id(),
            run_id=run_id,
            action_type=f"jira_{plan.action}",
            payload_hash=payload_hash,
            policy_version=POLICY_VERSION,
            requester_id=requester_id,
            approver_id=None,
            status=ApprovalStatus.PENDING.value,
            comment=None,
            created_at=now,
            decided_at=None,
            expires_at=None,
        )
        async with self.database.sessions() as session:
            session.add_all([action, approval])
            await session.commit()
        return action, approval

    async def get_action(self, action_id: str) -> JiraActionRow | None:
        async with self.database.sessions() as session:
            return await session.get(JiraActionRow, action_id)

    async def get_action_for_run(self, run_id: str) -> JiraActionRow | None:
        async with self.database.sessions() as session:
            return cast(
                JiraActionRow | None,
                await session.scalar(select(JiraActionRow).where(JiraActionRow.run_id == run_id)),
            )

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        async with self.database.sessions() as session:
            return await session.get(ApprovalRow, approval_id)

    async def decide_approval(
        self,
        *,
        action_id: str,
        approval_id: str,
        payload_hash: str,
        actor_id: str,
        status: ApprovalStatus,
        comment: str | None,
    ) -> ApprovalRow:
        async with self.database.sessions() as session:
            action = await session.get(JiraActionRow, action_id)
            approval = await session.get(ApprovalRow, approval_id)
            if action is None or approval is None or approval.run_id != action.run_id:
                raise ValueError("Jira action approval not found")
            if action.payload_hash != payload_hash or approval.payload_hash != payload_hash:
                raise ValueError("Approval payload hash mismatch")
            if approval.status != ApprovalStatus.PENDING.value:
                if approval.status == status.value and approval.approver_id == actor_id:
                    return approval
                raise ValueError("Approval is no longer pending")
            approval.status = status.value
            approval.approver_id = actor_id
            approval.comment = comment
            approval.decided_at = utc_now()
            action.status = status.value
            action.updated_at = utc_now()
            await session.commit()
            return approval

    async def approved_plan(
        self, *, action_id: str, approval_id: str, expected_hash: str
    ) -> JiraActionPlan:
        async with self.database.sessions() as session:
            action = await session.get(JiraActionRow, action_id)
            approval = await session.get(ApprovalRow, approval_id)
            if action is None or approval is None or approval.run_id != action.run_id:
                raise ValueError("Jira action approval not found")
            if action.payload_hash != expected_hash or approval.payload_hash != expected_hash:
                raise ValueError("Approval payload hash mismatch")
            if action.policy_version != POLICY_VERSION or approval.policy_version != POLICY_VERSION:
                raise ValueError("Jira action policy version changed")
            if approval.action_type != f"jira_{action.action_type}":
                raise ValueError("Jira action approval type mismatch")
            if approval.status != ApprovalStatus.APPROVED.value or action.status != "approved":
                raise ValueError("A current exact-payload approval is required")
            plan = JiraActionPlan.model_validate_json(action.payload_json)
            if hash_text(canonical_json(plan.approval_payload())) != expected_hash:
                raise ValueError("Persisted Jira action payload changed")
            action.status = "executing"
            action.updated_at = utc_now()
            await session.commit()
            return plan

    async def complete(self, action_id: str, result: dict[str, object]) -> None:
        async with self.database.sessions() as session:
            action = await session.get(JiraActionRow, action_id)
            if action is None:
                raise ValueError("Jira action not found")
            action.status = "completed"
            action.result_json = canonical_json(result)
            action.updated_at = utc_now()
            await session.commit()
