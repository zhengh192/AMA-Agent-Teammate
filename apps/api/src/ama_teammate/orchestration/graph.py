from __future__ import annotations

from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ama_teammate.orchestration.analysis_nodes import (
    build_analysis_node_functions,
    route_after_approval,
    stop_analysis_node,
)
from ama_teammate.orchestration.nodes import (
    assess_goal_node,
    clarification_node,
    intake_node,
    prepare_response_node,
)
from ama_teammate.orchestration.state import AgentState

if TYPE_CHECKING:
    from ama_teammate.services.analysis import AnalysisService


def build_graph(checkpointer: Any, analysis_service: AnalysisService | None = None) -> Any:
    builder = StateGraph(AgentState)
    builder.add_node("intake", intake_node)
    builder.add_node("assess_goal", assess_goal_node)
    builder.add_node("clarify", clarification_node)
    builder.add_node("prepare_response", prepare_response_node)

    def route_phase(state: AgentState) -> str:
        if state.get("missing_fields"):
            return "clarify"
        if state.get("route") == "analysis" and analysis_service is not None:
            return "analysis"
        return "prepare_response"

    routes: dict[Hashable, str] = {
        "clarify": "clarify",
        "prepare_response": "prepare_response",
    }
    if analysis_service is not None:
        create_plan, approve_sql, execute_analysis = build_analysis_node_functions(analysis_service)
        analysis_builder = StateGraph(AgentState)
        analysis_builder.add_node("create_analysis_plan", create_plan)
        analysis_builder.add_node("sql_approval", approve_sql)
        analysis_builder.add_node("execute_analysis", execute_analysis)
        analysis_builder.add_node("stop_analysis", stop_analysis_node)
        analysis_builder.add_edge(START, "create_analysis_plan")
        analysis_builder.add_edge("create_analysis_plan", "sql_approval")
        analysis_builder.add_conditional_edges(
            "sql_approval",
            route_after_approval,
            {"execute": "execute_analysis", "stop": "stop_analysis"},
        )
        analysis_builder.add_edge("execute_analysis", END)
        analysis_builder.add_edge("stop_analysis", END)
        builder.add_node("analysis", analysis_builder.compile())
        builder.add_edge("analysis", END)
        routes["analysis"] = "analysis"

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "assess_goal")
    builder.add_conditional_edges("assess_goal", route_phase, routes)
    builder.add_conditional_edges("clarify", route_phase, routes)
    builder.add_edge("prepare_response", END)
    return builder.compile(checkpointer=checkpointer)


class GraphRuntime:
    def __init__(self, graph: Any) -> None:
        self.graph = graph

    async def start(self, state: AgentState) -> dict[str, Any]:
        config = {"configurable": {"thread_id": state["run_id"]}}
        result = await self.graph.ainvoke(state, config=config)
        return dict(result)

    async def resume(self, run_id: str, value: Any) -> dict[str, Any]:
        config = {"configurable": {"thread_id": run_id}}
        result = await self.graph.ainvoke(Command(resume=value), config=config)
        return dict(result)

    @staticmethod
    def interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__")
        if not interrupts:
            return None
        value = getattr(interrupts[0], "value", None)
        return value if isinstance(value, dict) else {"question": str(value)}
