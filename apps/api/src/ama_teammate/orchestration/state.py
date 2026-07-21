from __future__ import annotations

from typing import Literal, TypedDict


class AgentState(TypedDict, total=False):
    schema_version: str
    session_id: str
    run_id: str
    user_id: str
    input_text: str
    combined_input: str
    route: Literal["chat", "analysis", "knowledge", "jira"]
    task_goal: str
    decision_summary: str
    task_steps: list[str]
    status: str
    analysis_question: str
    missing_fields: list[str]
    clarification_response: str
    role_context: str
    response_ready: bool
    plan_ref: str
    query_proposal_refs: list[str]
    dataset_refs: list[str]
    evidence_refs: list[str]
    chart_refs: list[str]
    pending_approval_ref: str
    approval_status: str
    analysis_result_ref: str
    final_answer_ref: str
    selected_skill_refs: list[dict[str, str]]
    jira_issue_keys: list[str]
    jira_status: str
    jira_fast_answer: str
    jira_action_type: str
    jira_action_json: str
    jira_action_ref: str
