from __future__ import annotations

import re
from typing import Any

from langgraph.types import interrupt

from ama_teammate.orchestration.state import AgentState
from ama_teammate.roles.data_analyst import PhaseOneDataAnalystMock
from ama_teammate.roles.knowledge_curator import PhaseOneKnowledgeCuratorMock

ANALYSIS_MARKERS = (
    "data",
    "database",
    "query",
    "sql",
    "metric",
    "trend",
    "why did",
    "分析",
    "数据",
    "查询",
    "指标",
    "趋势",
    "为什么",
)
KNOWLEDGE_MARKERS = ("document", "knowledge", "upload", "pdf", "docx", "文档", "知识", "上传")
METRIC_MARKERS = (
    "conversion",
    "revenue",
    "orders",
    "users",
    "rate",
    "count",
    "转化",
    "收入",
    "订单",
    "用户",
    "率",
    "数量",
)
TIME_MARKERS = (
    "today",
    "yesterday",
    "week",
    "month",
    "quarter",
    "year",
    "last",
    "since",
    "今天",
    "昨天",
    "周",
    "月",
    "季度",
    "年",
    "最近",
)
SOURCE_MARKERS = (
    "warehouse",
    "postgres",
    "mysql",
    "sql server",
    "table",
    "database",
    "source",
    "数仓",
    "数据库",
    "表",
    "数据源",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def intake_node(state: AgentState) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "combined_input": state.get("combined_input", state["input_text"]).strip(),
        "status": "planning",
    }


def assess_goal_node(state: AgentState) -> dict[str, Any]:
    text = state["input_text"].lower()
    if _contains_any(text, KNOWLEDGE_MARKERS):
        route = "knowledge"
        missing = (
            [] if re.search(r"\b[\w.-]+\.(pdf|docx|xlsx|csv|txt|md)\b", text) else ["document"]
        )
    elif _contains_any(text, ANALYSIS_MARKERS):
        route = "analysis"
        missing = []
        if not _contains_any(text, METRIC_MARKERS):
            missing.append("metric definition")
        if not _contains_any(text, TIME_MARKERS) and not re.search(r"\b20\d{2}\b", text):
            missing.append("time range and timezone")
        if not _contains_any(text, SOURCE_MARKERS):
            missing.append("approved data source")
    else:
        route = "chat"
        missing = []
    return {"route": route, "missing_fields": missing}


def route_after_assessment(state: AgentState) -> str:
    return "clarify" if state.get("missing_fields") else "prepare_response"


def clarification_node(state: AgentState) -> dict[str, Any]:
    missing = state.get("missing_fields", [])
    response = interrupt(
        {
            "kind": "clarification",
            "missing_fields": missing,
            "question": "Please provide: " + ", ".join(missing) + ".",
        }
    )
    answer = str(response).strip()
    return {
        "clarification_response": answer,
        "combined_input": f"{state['combined_input']}\nClarification: {answer}",
        "missing_fields": [],
        "status": "planning",
    }


def prepare_response_node(state: AgentState) -> dict[str, Any]:
    route = state.get("route", "chat")
    if route == "analysis":
        role_context = PhaseOneDataAnalystMock().phase_context()
    elif route == "knowledge":
        role_context = PhaseOneKnowledgeCuratorMock().phase_context()
    else:
        role_context = "Respond concisely and do not claim unperformed tool or data access."
    return {"role_context": role_context, "response_ready": True, "status": "executing"}
