from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select

from ama_teammate.analysis.models import (
    AnalysisPlan,
    AnalysisResult,
    Dataset,
    EvidenceRecord,
    JoinPlan,
    JoinQuality,
)
from ama_teammate.domain.models import ApprovalStatus, new_id, utc_now
from ama_teammate.sql_policy.models import ValidatedQuery
from ama_teammate.storage.analysis_schema import (
    AnalysisPlanRow,
    AnalysisResultRow,
    DatasetRow,
    EvidenceRow,
    JoinExecutionRow,
    QueryExecutionRow,
    QueryProposalRow,
)
from ama_teammate.storage.database import Database
from ama_teammate.storage.repositories import hash_text
from ama_teammate.storage.schema import ApprovalRow, ArtifactRow


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class AnalysisRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_plan_with_approval(
        self, plan: AnalysisPlan, requester_id: str
    ) -> tuple[AnalysisPlanRow, ApprovalRow]:
        now = utc_now()
        payload_json = canonical_json(plan.approval_payload())
        payload_hash = hash_text(payload_json)
        plan_row = AnalysisPlanRow(
            id=plan.id,
            run_id=plan.run_id,
            question_hash=hash_text(plan.question),
            goal=plan.goal,
            analysis_type=plan.intent.analysis_type.value,
            chart_type=plan.intent.chart_type.value,
            plan_json=plan.model_dump_json(),
            policy_version=plan.policy_version,
            status="waiting_approval",
            created_at=now,
            updated_at=now,
        )
        approval = ApprovalRow(
            id=new_id(),
            run_id=plan.run_id,
            action_type="execute_readonly_analysis_plan",
            payload_hash=payload_hash,
            policy_version=plan.policy_version,
            requester_id=requester_id,
            approver_id=None,
            status=ApprovalStatus.PENDING.value,
            comment=None,
            created_at=now,
            decided_at=None,
            expires_at=None,
        )
        query_rows = [self._query_row(plan.id, query, now) for query in plan.queries]
        async with self.database.sessions() as session:
            session.add_all([plan_row, approval, *query_rows])
            await session.commit()
        return plan_row, approval

    async def revise_plan_with_approval(
        self,
        plan: AnalysisPlan,
        requester_id: str,
    ) -> tuple[AnalysisPlanRow, ApprovalRow]:
        now = utc_now()
        payload_json = canonical_json(plan.approval_payload())
        approval = ApprovalRow(
            id=new_id(),
            run_id=plan.run_id,
            action_type="execute_readonly_analysis_plan",
            payload_hash=hash_text(payload_json),
            policy_version=plan.policy_version,
            requester_id=requester_id,
            approver_id=None,
            status=ApprovalStatus.PENDING.value,
            comment=None,
            created_at=now,
            decided_at=None,
            expires_at=None,
        )
        query_rows = [self._query_row(plan.id, query, now) for query in plan.queries]
        async with self.database.sessions() as session:
            plan_row = await session.get(AnalysisPlanRow, plan.id)
            if plan_row is None or plan_row.run_id != plan.run_id:
                raise ValueError("Analysis plan revision target was not found")
            plan_row.question_hash = hash_text(plan.question)
            plan_row.goal = plan.goal
            plan_row.analysis_type = plan.intent.analysis_type.value
            plan_row.chart_type = plan.intent.chart_type.value
            plan_row.plan_json = plan.model_dump_json()
            plan_row.policy_version = plan.policy_version
            plan_row.status = "waiting_approval"
            plan_row.updated_at = now
            session.add_all([approval, *query_rows])
            await session.commit()
            return plan_row, approval

    async def get_plan(self, plan_id: str) -> AnalysisPlan | None:
        async with self.database.sessions() as session:
            row = await session.get(AnalysisPlanRow, plan_id)
            return AnalysisPlan.model_validate_json(row.plan_json) if row else None

    async def get_plan_for_run(self, run_id: str) -> AnalysisPlan | None:
        async with self.database.sessions() as session:
            row = await session.scalar(
                select(AnalysisPlanRow)
                .where(AnalysisPlanRow.run_id == run_id)
                .order_by(AnalysisPlanRow.created_at.desc())
                .limit(1)
            )
            return AnalysisPlan.model_validate_json(row.plan_json) if row else None

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        async with self.database.sessions() as session:
            return await session.get(ApprovalRow, approval_id)

    async def get_run_approval(self, run_id: str) -> ApprovalRow | None:
        async with self.database.sessions() as session:
            return cast(
                ApprovalRow | None,
                await session.scalar(
                    select(ApprovalRow)
                    .where(ApprovalRow.run_id == run_id)
                    .order_by(ApprovalRow.created_at.desc())
                ),
            )

    async def decide_approval(
        self,
        approval_id: str,
        payload_hash: str,
        actor_id: str,
        status: ApprovalStatus,
        comment: str | None,
    ) -> ApprovalRow:
        async with self.database.sessions() as session:
            row = await session.get(ApprovalRow, approval_id)
            if row is None:
                raise ValueError("Approval not found")
            if row.payload_hash != payload_hash:
                raise ValueError("Approval payload hash mismatch")
            if row.status != ApprovalStatus.PENDING.value:
                if row.status == status.value and row.approver_id == actor_id:
                    return row
                raise ValueError("Approval is no longer pending")
            row.status = status.value
            row.approver_id = actor_id
            row.comment = comment
            row.decided_at = utc_now()
            plan_row = await session.scalar(
                select(AnalysisPlanRow)
                .where(AnalysisPlanRow.run_id == row.run_id)
                .order_by(AnalysisPlanRow.created_at.desc())
                .limit(1)
            )
            if plan_row is not None:
                plan_row.status = status.value
                plan_row.updated_at = utc_now()
            await session.commit()
            return row

    async def record_query_execution(
        self,
        run_id: str,
        query: ValidatedQuery,
        *,
        status: str,
        rows: int = 0,
        result_bytes: int = 0,
        duration_ms: float = 0,
        error_category: str | None = None,
        repair_attempt: int = 0,
    ) -> QueryExecutionRow:
        row = QueryExecutionRow(
            id=new_id(),
            run_id=run_id,
            proposal_id=query.proposal_id,
            source_id=query.source_id,
            actual_sql=query.normalized_sql,
            sql_hash=hash_text(query.normalized_sql),
            parameters_json=canonical_json(query.parameters),
            rows_returned=rows,
            result_bytes=result_bytes,
            duration_ms=duration_ms,
            repair_attempt=repair_attempt,
            status=status,
            error_category=error_category,
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def add_artifact(
        self,
        *,
        artifact_id: str,
        run_id: str,
        artifact_type: str,
        path: Path,
        content_hash: str,
    ) -> ArtifactRow:
        row = ArtifactRow(
            id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            storage_ref=str(path),
            content_hash=content_hash,
            classification="internal",
            status="available",
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def add_dataset(
        self, run_id: str, dataset: Dataset, artifact_id: str | None
    ) -> DatasetRow:
        row = DatasetRow(
            id=dataset.id,
            run_id=run_id,
            source_ids_json=canonical_json(dataset.source_ids),
            query_proposal_ids_json=canonical_json(dataset.query_proposal_ids),
            columns_json=canonical_json(dataset.columns),
            row_count=dataset.row_count,
            result_bytes=dataset.result_bytes,
            quality_json=dataset.quality.model_dump_json(),
            artifact_id=artifact_id,
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def add_join(
        self,
        run_id: str,
        plan_id: str,
        left_id: str,
        right_id: str,
        output_id: str,
        plan: JoinPlan,
        quality: JoinQuality,
    ) -> JoinExecutionRow:
        row = JoinExecutionRow(
            id=new_id(),
            run_id=run_id,
            plan_id=plan_id,
            left_dataset_id=left_id,
            right_dataset_id=right_id,
            output_dataset_id=output_id,
            join_plan_json=plan.model_dump_json(),
            quality_json=quality.model_dump_json(),
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            await session.commit()
            return row

    async def add_evidence(self, run_id: str, records: Sequence[EvidenceRecord]) -> None:
        rows = [
            EvidenceRow(
                id=item.id,
                run_id=run_id,
                title=item.title,
                dataset_ids_json=canonical_json(item.dataset_ids),
                query_proposal_ids_json=canonical_json(item.query_proposal_ids),
                calculation=item.calculation,
                support_json=canonical_json(item.support),
                epistemic_label=item.epistemic_label,
                confidence=item.confidence,
                limitations_json=canonical_json(item.limitations),
                created_at=utc_now(),
            )
            for item in records
        ]
        async with self.database.sessions() as session:
            session.add_all(rows)
            await session.commit()

    async def add_result(
        self, result: AnalysisResult, result_artifact_id: str
    ) -> AnalysisResultRow:
        row = AnalysisResultRow(
            id=result.id,
            run_id=result.run_id,
            plan_id=result.plan_id,
            result_artifact_id=result_artifact_id,
            csv_artifact_id=result.csv_artifact_id,
            status=result.status,
            created_at=utc_now(),
        )
        async with self.database.sessions() as session:
            session.add(row)
            plan = await session.get(AnalysisPlanRow, result.plan_id)
            if plan is not None:
                plan.status = "completed"
                plan.updated_at = utc_now()
            await session.commit()
            return row

    async def get_result_artifact_for_run(self, run_id: str) -> ArtifactRow | None:
        async with self.database.sessions() as session:
            row = await session.scalar(
                select(AnalysisResultRow)
                .where(AnalysisResultRow.run_id == run_id)
                .order_by(AnalysisResultRow.created_at.desc())
                .limit(1)
            )
            return await session.get(ArtifactRow, row.result_artifact_id) if row else None

    async def get_artifact(self, artifact_id: str) -> ArtifactRow | None:
        async with self.database.sessions() as session:
            return await session.get(ArtifactRow, artifact_id)

    async def list_query_executions(self, run_id: str) -> Sequence[QueryExecutionRow]:
        async with self.database.sessions() as session:
            result = await session.scalars(
                select(QueryExecutionRow)
                .where(QueryExecutionRow.run_id == run_id)
                .order_by(QueryExecutionRow.created_at)
            )
            return result.all()

    @staticmethod
    def _query_row(plan_id: str, query: ValidatedQuery, now: Any) -> QueryProposalRow:
        return QueryProposalRow(
            id=query.proposal_id,
            plan_id=plan_id,
            source_id=query.source_id,
            dialect=query.dialect,
            normalized_sql=query.normalized_sql,
            executable_sql=query.executable_sql,
            parameters_json=canonical_json(query.parameters),
            sql_hash=hash_text(query.normalized_sql),
            max_rows=query.max_rows,
            max_result_bytes=query.max_result_bytes,
            timeout_seconds=query.timeout_seconds,
            policy_version=query.policy_version,
            status="validated",
            created_at=now,
        )
