from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from ama_teammate.orchestration.state import AgentState
from ama_teammate.semantic_metadata.registry import MetadataAmbiguousError
from ama_teammate.services.analysis import AnalysisService


def build_analysis_node_functions(analysis_service: AnalysisService) -> tuple[Any, Any, Any]:
    async def create_analysis_plan(state: AgentState) -> dict[str, Any]:
        try:
            return await analysis_service.create_plan(dict(state))
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
