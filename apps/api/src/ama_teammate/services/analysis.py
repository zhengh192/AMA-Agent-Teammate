from __future__ import annotations

from typing import Any

from ama_teammate.analysis.artifacts import CSVArtifactWriter
from ama_teammate.analysis.charts import ChartBuilder
from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.join import BoundedDuckDBJoiner
from ama_teammate.analysis.json_artifacts import JSONArtifactStore
from ama_teammate.analysis.models import AnalysisPlan, AnalysisResult, Dataset
from ama_teammate.analysis.planner import AnalysisPlanner
from ama_teammate.analysis.quality import assess_dataset_quality
from ama_teammate.data_access.models import QueryExecutionFailure, QueryExecutionRequest
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.domain.models import ApprovalStatus, new_id, utc_now
from ama_teammate.evidence.validator import EvidenceValidator
from ama_teammate.learned_metrics.models import LearnedMetricDefinition
from ama_teammate.learned_metrics.service import LearnedMetricService
from ama_teammate.storage.analysis_repository import AnalysisRepository
from ama_teammate.storage.repositories import Repository, hash_text


class AnalysisService:
    def __init__(
        self,
        *,
        planner: AnalysisPlanner,
        registry: ConnectorRegistry,
        analysis_repository: AnalysisRepository,
        learned_metrics: LearnedMetricService,
        repository: Repository,
        joiner: BoundedDuckDBJoiner,
        engine: ControlledAnalysisEngine,
        chart_builder: ChartBuilder,
        evidence_validator: EvidenceValidator,
        csv_writer: CSVArtifactWriter,
        json_store: JSONArtifactStore,
    ) -> None:
        self.planner = planner
        self.registry = registry
        self.analysis_repository = analysis_repository
        self.learned_metrics = learned_metrics
        self.repository = repository
        self.joiner = joiner
        self.engine = engine
        self.chart_builder = chart_builder
        self.evidence_validator = evidence_validator
        self.csv_writer = csv_writer
        self.json_store = json_store

    async def create_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id = str(state["run_id"])
        user_id = str(state["user_id"])
        question = str(state.get("analysis_question", state.get("input_text", "")))
        context = str(state.get("combined_input", ""))
        plan = await self.planner.build(
            run_id, question, context=context, owner_id=user_id
        )
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="semantic_metadata.resolved",
            status="success",
            session_id=str(state["session_id"]),
            run_id=run_id,
            graph_node="create_analysis_plan",
            safe_details={
                "metric_definition_id": plan.metric_definition.id,
                "metric_definition_version": plan.metric_definition.version,
                "relationship_definitions": [
                    item.model_dump(mode="json") for item in plan.relationship_definitions
                ],
                "skill_execution_plan": [
                    item.model_dump(mode="json") for item in plan.skill_execution_plan
                ],
            },
        )
        _, approval = await self.analysis_repository.create_plan_with_approval(plan, user_id)
        await self.repository.add_audit_event(
            actor_id=user_id,
            event_type="analysis.plan.created",
            status="success",
            session_id=str(state["session_id"]),
            run_id=run_id,
            graph_node="create_analysis_plan",
            input_text=question,
            safe_details={
                "plan_id": plan.id,
                "analysis_type": plan.intent.analysis_type.value,
                "query_count": len(plan.queries),
                "source_ids": [query.source_id for query in plan.queries],
                "policy_version": plan.policy_version,
                "metric_definition_id": plan.metric_definition.id,
                "metric_definition_version": plan.metric_definition.version,
                "relationship_definitions": [
                    item.model_dump(mode="json") for item in plan.relationship_definitions
                ],
                "skill_execution_plan": [
                    item.model_dump(mode="json") for item in plan.skill_execution_plan
                ],
            },
        )
        return {
            "plan_ref": plan.id,
            "query_proposal_refs": [query.proposal_id for query in plan.queries],
            "pending_approval_ref": approval.id,
            "selected_skill_refs": [
                item.skill.model_dump(mode="json") for item in plan.skill_execution_plan
            ],
            "status": "waiting_approval",
        }

    async def learn_metric_from_clarification(
        self,
        state: dict[str, Any],
        *,
        metric_name: str,
        original_question: str,
        clarification: str,
    ) -> LearnedMetricDefinition:
        return await self.learned_metrics.learn_from_clarification(
            owner_id=str(state["user_id"]),
            metric_name=metric_name,
            original_question=original_question,
            clarification=clarification,
            session_id=str(state["session_id"]),
            run_id=str(state["run_id"]),
        )

    async def list_learned_metrics(self, owner_id: str) -> list[LearnedMetricDefinition]:
        return await self.learned_metrics.list_active(owner_id)
    async def get_learned_metric(
        self, owner_id: str, definition_id: str
    ) -> LearnedMetricDefinition | None:
        return await self.learned_metrics.get(owner_id, definition_id)

    async def search_learned_metrics(
        self, owner_id: str, query: str
    ) -> list[LearnedMetricDefinition]:
        return await self.learned_metrics.search(owner_id, query)
    async def approval_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = await self._require_plan(str(state["plan_ref"]))
        approval = await self.analysis_repository.get_approval(str(state["pending_approval_ref"]))
        if approval is None:
            raise ValueError("Approval not found")
        return {
            "kind": "sql_approval",
            "run_id": plan.run_id,
            "plan_id": plan.id,
            "approval_id": approval.id,
            "payload_hash": approval.payload_hash,
            "status": "waiting_approval",
            "plan": self.safe_plan(plan),
        }

    async def apply_decision(self, state: dict[str, Any], decision: Any) -> dict[str, Any]:
        if not isinstance(decision, dict):
            raise ValueError("Approval decision must be structured")
        try:
            status = ApprovalStatus(str(decision.get("status")))
        except ValueError as exc:
            raise ValueError("Invalid approval decision") from exc
        if status not in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CHANGES_REQUESTED,
        }:
            raise ValueError("Unsupported approval decision")
        approval_id = str(decision.get("approval_id", ""))
        payload_hash = str(decision.get("payload_hash", ""))
        if approval_id != str(state["pending_approval_ref"]):
            raise ValueError("Approval id mismatch")
        row = await self.analysis_repository.decide_approval(
            approval_id,
            payload_hash,
            str(state["user_id"]),
            status,
            str(decision.get("comment")) if decision.get("comment") else None,
        )
        await self.repository.add_audit_event(
            actor_id=str(state["user_id"]),
            event_type="analysis.approval.decided",
            status=row.status,
            session_id=str(state["session_id"]),
            run_id=str(state["run_id"]),
            graph_node="sql_approval",
            safe_details={"approval_id": row.id, "payload_hash": row.payload_hash},
        )
        return {
            "approval_status": row.status,
            "status": "executing" if row.status == ApprovalStatus.APPROVED.value else "cancelled",
        }

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = await self._require_plan(str(state["plan_ref"]))
        approval = await self.analysis_repository.get_approval(str(state["pending_approval_ref"]))
        if approval is None or approval.status != ApprovalStatus.APPROVED.value:
            raise ValueError("A current exact-payload approval is required")
        datasets: list[Dataset] = []
        for query in plan.queries:
            connector = self.registry.get(query.source_id)
            try:
                execution = await connector.execute(
                    QueryExecutionRequest(
                        source_id=query.source_id,
                        sql=query.executable_sql,
                        parameters=query.parameters,
                        timeout_seconds=query.timeout_seconds,
                        max_rows=query.max_rows,
                        max_result_bytes=query.max_result_bytes,
                    )
                )
            except QueryExecutionFailure as exc:
                await self.analysis_repository.record_query_execution(
                    plan.run_id,
                    query,
                    status="failed",
                    error_category=exc.category,
                )
                if exc.category == "syntax":
                    repaired = self.planner.repair_syntax(query)
                    await self.repository.add_audit_event(
                        actor_id=str(state["user_id"]),
                        event_type="query.repair.proposed",
                        status="stopped",
                        session_id=str(state["session_id"]),
                        run_id=plan.run_id,
                        graph_node="execute_analysis",
                        safe_details={
                            "proposal_id": query.proposal_id,
                            "repair_attempts": 1,
                            "repair_sql_hash": hash_text(repaired.executable_sql),
                            "changed": repaired.executable_sql != query.executable_sql,
                            "reason": "Changed SQL requires a new approval.",
                        },
                    )
                    raise QueryExecutionFailure(
                        "syntax",
                        "One syntax repair was proposed; changed SQL requires a new approval.",
                    ) from exc
                raise
            await self.analysis_repository.record_query_execution(
                plan.run_id,
                query,
                status="success",
                rows=execution.row_count,
                result_bytes=execution.result_bytes,
                duration_ms=execution.duration_ms,
            )
            dataset = Dataset(
                id=new_id(),
                source_ids=[query.source_id],
                query_proposal_ids=[query.proposal_id],
                columns=execution.columns,
                rows=execution.rows,
                row_count=execution.row_count,
                result_bytes=execution.result_bytes,
                quality=assess_dataset_quality(execution.rows, execution.columns),
            )
            await self.analysis_repository.add_dataset(plan.run_id, dataset, None)
            datasets.append(dataset)
            await self.repository.add_audit_event(
                actor_id=str(state["user_id"]),
                event_type="query.executed",
                status="success",
                session_id=str(state["session_id"]),
                run_id=plan.run_id,
                graph_node="execute_analysis",
                safe_details={
                    "proposal_id": query.proposal_id,
                    "source_id": query.source_id,
                    "rows": execution.row_count,
                    "result_bytes": execution.result_bytes,
                    "duration_ms": round(execution.duration_ms, 3),
                },
            )

        join_quality = None
        final_dataset = datasets[0]
        if plan.join_plan is not None:
            final_dataset, join_quality = self.joiner.join(datasets[0], datasets[1], plan.join_plan)
            await self.analysis_repository.add_dataset(plan.run_id, final_dataset, None)
            await self.analysis_repository.add_join(
                plan.run_id,
                plan.id,
                datasets[0].id,
                datasets[1].id,
                final_dataset.id,
                plan.join_plan,
                join_quality,
            )
            datasets.append(final_dataset)
        computation = self.engine.analyze(plan.intent, final_dataset, join_quality)
        self.evidence_validator.validate(computation)
        await self.analysis_repository.add_evidence(plan.run_id, computation.evidence)
        chart = self.chart_builder.build(plan.intent, final_dataset, computation)
        confirmed_findings = [
            item for item in computation.conclusions if item.epistemic_label == "Confirmed"
        ]
        inferred_findings = [
            item for item in computation.conclusions if item.epistemic_label == "Inferred"
        ]
        unknowns = [
            item.text for item in computation.conclusions if item.epistemic_label == "Unknown"
        ]
        limitations = sorted(
            {limitation for item in computation.evidence for limitation in item.limitations}
        )
        confidence = final_dataset.quality.confidence
        recommendations = (
            ["Resolve data-quality limitations before relying on this analysis."]
            if confidence.value in {"low", "unusable"}
            else ["Use the linked evidence and approved definitions for follow-up decisions."]
        )
        executive_summary = f"Completed {plan.intent.analysis_type.value} analysis with {confidence.value} data confidence."

        csv_id, csv_path, csv_hash = self.csv_writer.write(plan.run_id, final_dataset)
        await self.analysis_repository.add_artifact(
            artifact_id=csv_id,
            run_id=plan.run_id,
            artifact_type="bounded_csv",
            path=csv_path,
            content_hash=csv_hash,
        )
        result = AnalysisResult(
            id=new_id(),
            run_id=plan.run_id,
            plan_id=plan.id,
            status="completed",
            datasets=datasets,
            join_quality=join_quality,
            computation=computation,
            chart=chart,
            csv_artifact_id=csv_id,
            completed_at=utc_now().isoformat(),
            executive_summary=executive_summary,
            confirmed_findings=confirmed_findings,
            inferred_findings=inferred_findings,
            unknowns=unknowns,
            recommendations=recommendations,
            limitations=limitations,
            evidence=computation.evidence,
            charts=[chart],
            metric_references=[plan.metric_definition],
            data_source_references=sorted({query.source_id for query in plan.queries}),
            executed_query_references=[query.proposal_id for query in plan.queries],
            skill_references=[item.skill for item in plan.skill_execution_plan],
            data_confidence=confidence,
        )
        result_artifact_id, result_path, result_hash = self.json_store.write_result(result)
        await self.analysis_repository.add_artifact(
            artifact_id=result_artifact_id,
            run_id=plan.run_id,
            artifact_type="analysis_result_json",
            path=result_path,
            content_hash=result_hash,
        )
        await self.analysis_repository.add_result(result, result_artifact_id)
        await self.repository.add_audit_event(
            actor_id=str(state["user_id"]),
            event_type="analysis.completed",
            status="success",
            session_id=str(state["session_id"]),
            run_id=plan.run_id,
            graph_node="execute_analysis",
            safe_details={
                "result_id": result.id,
                "dataset_id": final_dataset.id,
                "evidence_ids": [item.id for item in computation.evidence],
                "chart_type": chart.chart_type.value,
                "data_confidence": confidence.value,
                "skill_references": [
                    item.skill.model_dump(mode="json") for item in plan.skill_execution_plan
                ],
            },
        )
        return {
            "analysis_result_ref": result.id,
            "final_answer_ref": result_artifact_id,
            "status": "completed",
        }

    async def result_for_run(self, run_id: str) -> AnalysisResult | None:
        artifact = await self.analysis_repository.get_result_artifact_for_run(run_id)
        return (
            self.json_store.read_result(self._artifact_path(artifact.storage_ref))
            if artifact
            else None
        )

    async def safe_plan_for_run(self, run_id: str) -> dict[str, Any] | None:
        plan = await self.analysis_repository.get_plan_for_run(run_id)
        if plan is None:
            return None
        approval = await self.analysis_repository.get_run_approval(run_id)
        value = self.safe_plan(plan)
        value["approval"] = (
            {
                "id": approval.id,
                "status": approval.status,
                "payload_hash": approval.payload_hash,
            }
            if approval
            else None
        )
        return value

    @staticmethod
    def safe_plan(plan: AnalysisPlan) -> dict[str, Any]:
        return {
            "id": plan.id,
            "goal": plan.goal,
            "analysis_type": plan.intent.analysis_type.value,
            "metric": plan.intent.metric,
            "dimensions": plan.intent.dimensions,
            "chart_type": plan.intent.chart_type.value,
            "success_criteria": plan.intent.success_criteria,
            "metadata_confidence": plan.intent.metadata_confidence,
            "assumptions": plan.intent.assumptions,
            "queries": [
                {
                    "id": query.proposal_id,
                    "source_id": query.source_id,
                    "dialect": query.dialect,
                    "sql": query.normalized_sql,
                    "parameters": query.parameters,
                    "max_rows": query.max_rows,
                    "max_result_bytes": query.max_result_bytes,
                    "timeout_seconds": query.timeout_seconds,
                    "policy_version": query.policy_version,
                }
                for query in plan.queries
            ],
            "join_plan": plan.join_plan.model_dump() if plan.join_plan else None,
            "policy_version": plan.policy_version,
            "metric_definition": plan.metric_definition.model_dump(mode="json"),
            "relationship_definitions": [
                item.model_dump(mode="json") for item in plan.relationship_definitions
            ],
            "skill_execution_plan": [
                item.model_dump(mode="json") for item in plan.skill_execution_plan
            ],
        }

    async def _require_plan(self, plan_id: str) -> AnalysisPlan:
        plan = await self.analysis_repository.get_plan(plan_id)
        if plan is None:
            raise ValueError("Analysis plan not found")
        return plan

    def _artifact_path(self, value: str) -> Any:
        from pathlib import Path

        return Path(value)
