from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from ama_teammate.analysis.planner import AnalysisDefinitionNeedsClarification
from ama_teammate.learned_metrics.models import (
    LearnedMetricAmbiguousError,
    MetricLearningInputError,
    MetricLearningRequired,
)
from ama_teammate.orchestration.state import AgentState
from ama_teammate.semantic_metadata.registry import (
    MetadataAmbiguousError,
    MetadataResolutionError,
)
from ama_teammate.services.analysis import AnalysisService


def build_analysis_node_functions(analysis_service: AnalysisService) -> tuple[Any, Any, Any]:
    async def create_analysis_plan(state: AgentState) -> dict[str, Any]:
        try:
            return await analysis_service.create_plan(dict(state))
        except LearnedMetricAmbiguousError as exc:
            response = interrupt(
                {
                    "kind": "learned_metric_clarification",
                    "question": "我找到了多个相近的已学习指标，请回复一个准确名称。",
                    "missing_fields": ["learned_metric_name"],
                    "options": [
                        {
                            "id": item.id,
                            "name": item.display_name,
                            "version": item.version,
                            "aliases": item.aliases,
                        }
                        for item in exc.candidates
                    ],
                }
            )
            revised = dict(state)
            original = str(state.get("combined_input", state.get("input_text", "")))
            revised["combined_input"] = f"{original}\nMetric name confirmation: {response}"
            revised["analysis_question"] = (
                f"{state.get('input_text', '')}\nMetric name confirmation: {response}"
            )
            return await analysis_service.create_plan(revised)
        except MetricLearningRequired as exc:
            answers: list[str] = []
            correction_message: str | None = None
            while True:
                response = interrupt(
                    {
                        "kind": (
                            "metric_definition_correction"
                            if correction_message
                            else "metric_definition_required"
                        ),
                        "question": correction_message or exc.prompt,
                        "metric_name": exc.metric_name,
                        "missing_fields": (
                            ["metric_definition_detail"]
                            if correction_message
                            else exc.missing_fields
                        ),
                        "example": exc.example,
                    }
                )
                answer = str(response).strip()
                if answer:
                    answers.append(answer)
                combined_answer = "\n".join(answers)
                candidate_state = dict(state)
                candidate_state["analysis_question"] = f"{exc.question}\n{combined_answer}"
                candidate_state["combined_input"] = (
                    f"{state.get('combined_input', state.get('input_text', ''))}\n"
                    f"Field clarification:\n{combined_answer}"
                )
                try:
                    return await analysis_service.create_plan(candidate_state)
                except (MetricLearningRequired, AnalysisDefinitionNeedsClarification):
                    pass
                try:
                    learned = await analysis_service.learn_metric_from_clarification(
                        dict(state),
                        metric_name=exc.metric_name,
                        original_question=exc.question,
                        clarification=combined_answer,
                    )
                    break
                except MetricLearningInputError as parse_error:
                    correction_message = (
                        "前面说过的我都记着，不用从头再来。"
                        f"现在还有一点没对上：{parse_error}"
                        "你把这一点告诉我，我就接着往下做。"
                    )
            revised = dict(state)
            original = str(state.get("combined_input", state.get("input_text", "")))
            revised["combined_input"] = (
                f"{original}\nConfirmed learned metric: {learned.display_name} "
                f"version {learned.version}."
            )
            revised["analysis_question"] = (
                f"{state.get('input_text', exc.question)}\n{combined_answer}"
            )
            return await analysis_service.create_plan(revised)
        except MetadataAmbiguousError as exc:
            response = interrupt(
                {
                    "kind": "semantic_metadata_clarification",
                    "question": "Multiple approved metrics match. Please choose an exact metric ID.",
                    "missing_fields": ["metric_definition_id"],
                    "options": [
                        {"id": item.id, "version": item.version, "name": item.name}
                        for item in exc.matches
                    ],
                }
            )
            revised = dict(state)
            original = str(state.get("combined_input", state.get("input_text", "")))
            revised["combined_input"] = f"{original}\nMetric clarification: {response}"
            revised["analysis_question"] = (
                f"{state.get('input_text', '')}\nMetric clarification: {response}"
            )
            return await analysis_service.create_plan(revised)
        except (MetadataResolutionError, AnalysisDefinitionNeedsClarification) as exc:
            response = interrupt(
                {
                    "kind": "analysis_definition_clarification",
                    "question": (
                        f"Current pilot understanding is incomplete: {exc} "
                        "Reply with your intended metric meaning, numerator/denominator, "
                        "or field interpretation and I will revise the plan."
                    ),
                    "missing_fields": ["working_metric_definition"],
                }
            )
            revised = dict(state)
            original = str(state.get("combined_input", state.get("input_text", "")))
            revised["combined_input"] = f"{original}\nWorking definition correction: {response}"
            revised["analysis_question"] = (
                f"{state.get('input_text', '')}\nWorking definition correction: {response}"
            )
            return await analysis_service.create_plan(revised)

    async def sql_approval(state: AgentState) -> dict[str, Any]:
        payload = await analysis_service.approval_payload(dict(state))
        decision = interrupt(payload)
        return await analysis_service.apply_decision(dict(state), decision)

    async def execute_analysis(state: AgentState) -> dict[str, Any]:
        return await analysis_service.execute(dict(state))

    return create_analysis_plan, sql_approval, execute_analysis


def route_after_approval(state: AgentState) -> str:
    return "execute" if state.get("approval_status") == "approved" else "stop"


def stop_analysis_node(state: AgentState) -> dict[str, Any]:
    del state
    return {"status": "cancelled"}
