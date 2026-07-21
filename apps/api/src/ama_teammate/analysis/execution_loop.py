from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ama_teammate.analysis.models import (
    AnalysisLoopReview,
    AnalysisPlan,
    AnalysisResult,
    AnalysisStepResult,
    Dataset,
)
from ama_teammate.analysis.python_sandbox import (
    PythonSandboxRequest,
    PythonSandboxUnavailable,
    PythonTransformProgram,
)
from ama_teammate.analysis.quality import assess_dataset_quality
from ama_teammate.data_access.models import QueryExecutionFailure, QueryExecutionRequest
from ama_teammate.domain.models import ApprovalStatus, new_id, utc_now
from ama_teammate.providers.base import ProviderMessage, StructuredProviderRequest
from ama_teammate.storage.repositories import hash_text

if TYPE_CHECKING:
    from ama_teammate.services.analysis import AnalysisService


async def execute_analysis_step(
    service: AnalysisService,
    state: dict[str, Any],
) -> dict[str, Any]:
    plan = await service._require_plan(str(state["plan_ref"]))
    approval = await service.analysis_repository.get_approval(str(state["pending_approval_ref"]))
    if approval is None or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError("A current exact-payload approval is required")

    datasets: list[Dataset] = []
    for query in plan.queries:
        connector = service.registry.get(query.source_id)
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
            await service.analysis_repository.record_query_execution(
                plan.run_id,
                query,
                status="failed",
                error_category=exc.category,
            )
            if exc.category == "syntax":
                repaired = service.planner.repair_syntax(query)
                await service.repository.add_audit_event(
                    actor_id=str(state["user_id"]),
                    event_type="query.repair.proposed",
                    status="stopped",
                    session_id=str(state["session_id"]),
                    run_id=plan.run_id,
                    graph_node="execute_analysis_step",
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

        await service.analysis_repository.record_query_execution(
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
        await service.analysis_repository.add_dataset(plan.run_id, dataset, None)
        datasets.append(dataset)
        await service.repository.add_audit_event(
            actor_id=str(state["user_id"]),
            event_type="query.executed",
            status="success",
            session_id=str(state["session_id"]),
            run_id=plan.run_id,
            graph_node="execute_analysis_step",
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
        final_dataset, join_quality = service.joiner.join(
            datasets[0],
            datasets[1],
            plan.join_plan,
        )
        await service.analysis_repository.add_dataset(plan.run_id, final_dataset, None)
        await service.analysis_repository.add_join(
            plan.run_id,
            plan.id,
            datasets[0].id,
            datasets[1].id,
            final_dataset.id,
            plan.join_plan,
            join_quality,
        )
        datasets.append(final_dataset)

    if "python_sandbox" in plan.intent.preferred_tools:
        transformed = await _apply_python_transform(
            service,
            state,
            plan,
            final_dataset,
        )
        if transformed is not None:
            final_dataset = transformed
            datasets.append(transformed)
            await service.analysis_repository.add_dataset(plan.run_id, transformed, None)

    computation = service.engine.analyze(plan.intent, final_dataset, join_quality)
    service.evidence_validator.validate(computation)
    await service.analysis_repository.add_evidence(plan.run_id, computation.evidence)
    chart = service.chart_builder.build(plan.intent, final_dataset, computation)
    iteration = int(state.get("analysis_loop_iteration", 0)) + 1
    step = AnalysisStepResult(
        iteration=iteration,
        plan_id=plan.id,
        intent=plan.intent,
        datasets=datasets,
        final_dataset_id=final_dataset.id,
        join_quality=join_quality,
        computation=computation,
        chart=chart,
        metric_reference=plan.metric_definition,
        business_rule_references=plan.business_rule_definitions,
        executed_query_references=[query.proposal_id for query in plan.queries],
        data_source_references=sorted({query.source_id for query in plan.queries}),
        skill_references=[item.skill for item in plan.skill_execution_plan],
    )
    previous = list(state.get("analysis_step_results", []))
    previous.append(step.model_dump(mode="json"))
    return {
        "analysis_loop_iteration": iteration,
        "analysis_step_results": previous,
        "dataset_refs": [item.id for item in datasets],
        "evidence_refs": [item.id for item in computation.evidence],
        "status": "reviewing",
    }


async def review_analysis_step(
    service: AnalysisService,
    state: dict[str, Any],
) -> dict[str, Any]:
    plan = await service._require_plan(str(state["plan_ref"]))
    steps = [
        AnalysisStepResult.model_validate(item) for item in state.get("analysis_step_results", [])
    ]
    if not steps:
        raise ValueError("Analysis loop has no executed step to review")
    methods: list[dict[str, Any]] = []
    if service.planner.skill_registry is not None:
        for reference in steps[-1].skill_references:
            package = service.planner.skill_registry.get(reference.id, reference.version)
            methods.append(
                {
                    "id": reference.id,
                    "version": reference.version,
                    "description": package.metadata.description,
                    "method": package.instructions[:4_000],
                }
            )
    observations = list(state.get("analysis_loop_observations", []))
    try:
        review = await service.analysis_loop.review(
            original_question=str(state.get("input_text", plan.question)),
            plan=plan,
            step=steps[-1],
            prior_observations=observations,
            skill_methods=methods,
        )
    except Exception:
        review = service.analysis_loop.finish_review(plan, steps[-1])
    observations.append(review.observation)
    learning = list(state.get("analysis_learning_candidates", []))
    learning.extend(item.model_dump(mode="json") for item in review.learning_candidates)
    await service.repository.add_audit_event(
        actor_id=str(state["user_id"]),
        event_type="analysis.loop.reviewed",
        status="success",
        session_id=str(state["session_id"]),
        run_id=plan.run_id,
        graph_node="review_analysis_step",
        safe_details={
            "iteration": steps[-1].iteration,
            "decision": review.decision,
            "has_next_question": bool(review.next_question),
            "learning_candidate_count": len(review.learning_candidates),
        },
    )
    return {
        "analysis_loop_review": review.model_dump(mode="json"),
        "analysis_loop_decision": review.decision,
        "analysis_loop_observations": observations,
        "analysis_learning_candidates": learning,
        "status": "planning" if review.decision == "continue" else "executing",
    }


async def prepare_followup_plan(
    service: AnalysisService,
    state: dict[str, Any],
) -> dict[str, Any]:
    review = AnalysisLoopReview.model_validate(state["analysis_loop_review"])
    if review.decision != "continue" or not review.next_question:
        raise ValueError("Analysis loop did not request a follow-up plan")
    revised = dict(state)
    revised["analysis_question"] = review.next_question
    revised["combined_input"] = (
        f"{state.get('combined_input', state.get('input_text', ''))}\n"
        f"<analysis_observation>{review.observation}</analysis_observation>\n"
        f"<next_analytical_step>{review.next_question}</next_analytical_step>"
    )
    plan = await service.planner.build(
        str(state["run_id"]),
        review.next_question,
        context=str(revised["combined_input"]),
        owner_id=str(state["user_id"]),
    )
    plan = plan.model_copy(update={"id": str(state["plan_ref"])})
    _, approval = await service.analysis_repository.revise_plan_with_approval(
        plan,
        str(state["user_id"]),
    )
    await service.repository.add_audit_event(
        actor_id=str(state["user_id"]),
        event_type="analysis.plan.revised",
        status="success",
        session_id=str(state["session_id"]),
        run_id=plan.run_id,
        graph_node="create_followup_plan",
        input_text=review.next_question,
        safe_details={
            "plan_id": plan.id,
            "iteration": int(state.get("analysis_loop_iteration", 0)) + 1,
            "query_count": len(plan.queries),
            "source_ids": [query.source_id for query in plan.queries],
            "policy_version": plan.policy_version,
        },
    )
    return {
        "plan_ref": plan.id,
        "query_proposal_refs": [query.proposal_id for query in plan.queries],
        "pending_approval_ref": approval.id,
        "selected_skill_refs": [
            item.skill.model_dump(mode="json") for item in plan.skill_execution_plan
        ],
        "analysis_question": review.next_question,
        "combined_input": revised["combined_input"],
        "approval_status": ApprovalStatus.PENDING.value,
        "status": "waiting_approval",
    }


async def _apply_python_transform(
    service: AnalysisService,
    state: dict[str, Any],
    plan: AnalysisPlan,
    dataset: Dataset,
) -> Dataset | None:
    schema = {
        column: sorted(
            {
                type(row.get(column)).__name__
                for row in dataset.rows[:20]
                if row.get(column) is not None
            }
        )
        for column in dataset.columns
    }
    prompt = {
        "goal": plan.intent.user_goal or plan.goal,
        "analysis_type": plan.intent.analysis_type.value,
        "columns_and_types": schema,
        "row_limit": dataset.row_count,
        "contract": (
            'Read rows from datasets["input"]. Assign a JSON-compatible dict to result with '
            "a rows key containing the transformed list of row objects. Use only the Python "
            "standard library. Do not import networking, process, filesystem, or reflection APIs."
        ),
    }
    generated = await service.planner.providers.provider.generate_structured(
        [
            ProviderMessage(
                role="developer",
                content=(
                    "Generate a bounded Python transformation only when SQL and the controlled "
                    "analysis library are insufficient. Return the strict program schema. The "
                    "code runs in an isolated no-network container and must assign result. "
                    "Never include source data values in the code."
                ),
            ),
            ProviderMessage(
                role="user",
                content=json.dumps(prompt, ensure_ascii=False),
            ),
        ],
        service.planner.providers.analyst,
        StructuredProviderRequest(
            name="python_transform_program",
            schema=PythonTransformProgram,
        ),
    )
    if not isinstance(generated, PythonTransformProgram):
        raise TypeError("Provider returned an invalid Python transform program")
    try:
        sandbox_result = await service.python_sandbox.execute(
            PythonSandboxRequest(
                code=generated.code,
                datasets={"input": dataset.rows},
            )
        )
    except PythonSandboxUnavailable as exc:
        await service.repository.add_audit_event(
            actor_id=str(state["user_id"]),
            event_type="analysis.python_sandbox.unavailable",
            status="stopped",
            session_id=str(state["session_id"]),
            run_id=plan.run_id,
            graph_node="execute_analysis_step",
            safe_details={"reason": str(exc)[:500]},
        )
        return None

    rows = sandbox_result.output.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) > 2_000
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("Sandbox rows violate the bounded output contract")
    normalized_rows = [{str(key): value for key, value in row.items()} for row in rows]
    columns = list(normalized_rows[0]) if normalized_rows else dataset.columns
    result_bytes = len(json.dumps(normalized_rows, ensure_ascii=False, default=str).encode("utf-8"))
    transformed = Dataset(
        id=new_id(),
        source_ids=dataset.source_ids,
        query_proposal_ids=dataset.query_proposal_ids,
        columns=columns,
        rows=normalized_rows,
        row_count=len(normalized_rows),
        result_bytes=result_bytes,
        quality=assess_dataset_quality(normalized_rows, columns),
    )
    await service.repository.add_audit_event(
        actor_id=str(state["user_id"]),
        event_type="analysis.python_sandbox.executed",
        status="success",
        session_id=str(state["session_id"]),
        run_id=plan.run_id,
        graph_node="execute_analysis_step",
        safe_details={
            "input_rows": dataset.row_count,
            "output_rows": transformed.row_count,
            "result_bytes": transformed.result_bytes,
            "purpose": generated.purpose,
        },
    )
    return transformed


async def finalize_analysis_steps(
    service: AnalysisService,
    state: dict[str, Any],
) -> dict[str, Any]:
    steps = [
        AnalysisStepResult.model_validate(item) for item in state.get("analysis_step_results", [])
    ]
    if not steps:
        raise ValueError("Analysis loop has no result to finalize")

    last_step = steps[-1]
    last_plan = await service._require_plan(last_step.plan_id)
    final_dataset = next(
        item for item in last_step.datasets if item.id == last_step.final_dataset_id
    )
    datasets = [dataset for step in steps for dataset in step.datasets]
    evidence = [item for step in steps for item in step.computation.evidence]
    conclusions = [item for step in steps for item in step.computation.conclusions]
    confirmed_findings = [item for item in conclusions if item.epistemic_label == "Confirmed"]
    inferred_findings = [item for item in conclusions if item.epistemic_label == "Inferred"]
    unknowns = [item.text for item in conclusions if item.epistemic_label == "Unknown"]
    limitations = sorted({limitation for item in evidence for limitation in item.limitations})
    confidence = final_dataset.quality.confidence
    chinese = last_plan.intent.response_language == "zh-CN"
    if confidence.value in {"low", "unusable"}:
        recommendations = [
            "先处理结果中列出的数据质量问题，再使用这些结论。"
            if chinese
            else "Resolve the listed data-quality issues before using these findings."
        ]
    elif len(steps) >= service.analysis_loop.max_iterations:
        recommendations = [
            "本轮已经达到自动分析步数上限；如需继续，我会从当前证据接着查。"
            if chinese
            else (
                "This run reached the autonomous step limit; a follow-up can continue from "
                "the current evidence."
            )
        ]
    else:
        recommendations = [
            "如果还要深入，我会从当前证据继续拆解，而不是重新开始。"
            if chinese
            else "A follow-up can continue from the current evidence without starting over."
        ]
    executive_summary = (
        f"我完成了 {len(steps)} 个有边界的分析步骤，结果和依据如下。"
        if chinese
        else f"I completed {len(steps)} bounded analysis step(s); results and evidence follow."
    )

    csv_id, csv_path, csv_hash = service.csv_writer.write(
        last_plan.run_id,
        final_dataset,
    )
    await service.analysis_repository.add_artifact(
        artifact_id=csv_id,
        run_id=last_plan.run_id,
        artifact_type="bounded_csv",
        path=csv_path,
        content_hash=csv_hash,
    )

    metric_references = _unique_models(
        [step.metric_reference for step in steps],
        key=lambda item: (item.definition_type.value, item.id, item.version),
    )
    business_rules = _unique_models(
        [item for step in steps for item in step.business_rule_references],
        key=lambda item: (item.definition_type.value, item.id, item.version),
    )
    skill_references = _unique_models(
        [item for step in steps for item in step.skill_references],
        key=lambda item: (item.id, item.version),
    )
    learning_candidates = [
        item for item in state.get("analysis_learning_candidates", []) if isinstance(item, dict)
    ]
    result = AnalysisResult(
        id=new_id(),
        run_id=last_plan.run_id,
        plan_id=last_plan.id,
        status="completed",
        datasets=datasets,
        join_quality=last_step.join_quality,
        computation=last_step.computation,
        chart=last_step.chart,
        csv_artifact_id=csv_id,
        completed_at=utc_now().isoformat(),
        executive_summary=executive_summary,
        confirmed_findings=confirmed_findings,
        inferred_findings=inferred_findings,
        unknowns=unknowns,
        recommendations=recommendations,
        limitations=limitations,
        evidence=evidence,
        charts=[item.chart for item in steps],
        metric_references=metric_references,
        data_source_references=sorted({source for item in datasets for source in item.source_ids}),
        executed_query_references=[
            query_ref for step in steps for query_ref in step.executed_query_references
        ],
        business_rule_references=business_rules,
        skill_references=skill_references,
        data_confidence=confidence,
        loop_observations=list(state.get("analysis_loop_observations", [])),
        learning_candidates=learning_candidates,
    )
    result_artifact_id, result_path, result_hash = service.json_store.write_result(result)
    await service.analysis_repository.add_artifact(
        artifact_id=result_artifact_id,
        run_id=last_plan.run_id,
        artifact_type="analysis_result_json",
        path=result_path,
        content_hash=result_hash,
    )
    await service.analysis_repository.add_result(result, result_artifact_id)
    await service.repository.add_audit_event(
        actor_id=str(state["user_id"]),
        event_type="analysis.completed",
        status="success",
        session_id=str(state["session_id"]),
        run_id=last_plan.run_id,
        graph_node="finalize_analysis",
        safe_details={
            "result_id": result.id,
            "dataset_id": final_dataset.id,
            "evidence_count": len(evidence),
            "analysis_iterations": len(steps),
            "chart_count": len(result.charts),
            "data_confidence": confidence.value,
            "learning_candidate_count": len(result.learning_candidates),
        },
    )
    return {
        "analysis_result_ref": result.id,
        "final_answer_ref": result_artifact_id,
        "status": "completed",
    }


def _unique_models(values: list[Any], *, key: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for item in values:
        identity = key(item)
        if identity not in seen:
            seen.add(identity)
            result.append(item)
    return result
