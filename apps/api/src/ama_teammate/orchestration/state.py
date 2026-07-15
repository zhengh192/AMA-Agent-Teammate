from __future__ import annotations

from typing import Literal, TypedDict


class AgentState(TypedDict, total=False):
    schema_version: str
    session_id: str
    run_id: str
    user_id: str
    input_text: str
    combined_input: str
    route: Literal["chat", "analysis", "knowledge"]
    status: str
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
