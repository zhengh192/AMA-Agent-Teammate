from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from ama_teammate.jira.models import JiraActionPlan
from ama_teammate.jira.service import JiraReadService
from ama_teammate.orchestration.state import AgentState


def build_jira_node_functions(jira_service: JiraReadService) -> tuple[Any, Any, Any]:
    async def plan_jira_action(state: AgentState) -> dict[str, Any]:
        planned = await jira_service.prepare_action(dict(state))
        plan = JiraActionPlan.model_validate_json(str(planned["jira_action_json"]))
        if plan.action != "clarify":
            return planned
        response = interrupt(
            {
                "kind": "jira_action_clarification",
                "question": plan.clarification_question,
                "missing_fields": ["jira_action_details"],
            }
        )
        revised = dict(state)
        answer = str(response).strip()
        revised["input_text"] = f"{state.get('input_text', '')}\n补充：{answer}"
        revised["combined_input"] = (
            f"{state.get('combined_input', '')}\nJira action clarification: {answer}"
        )
        return await jira_service.prepare_action(revised)

    async def approve_jira_action(state: AgentState) -> dict[str, Any]:
        payload = await jira_service.approval_payload(dict(state))
        if payload is None:
            return {"approval_status": "approved", "status": "executing"}
        decision = interrupt(payload)
        return await jira_service.apply_decision(dict(state), decision)

    async def execute_jira_action(state: AgentState) -> dict[str, Any]:
        return await jira_service.execute_action(dict(state))

    return plan_jira_action, approve_jira_action, execute_jira_action


def route_after_jira_approval(state: AgentState) -> str:
    return "execute" if state.get("approval_status") == "approved" else "stop"


def stop_jira_action(state: AgentState) -> dict[str, Any]:
    del state
    return {"status": "cancelled"}
