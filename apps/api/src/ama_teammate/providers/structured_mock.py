from __future__ import annotations

import json
import re
from typing import Any


def goal_assessment_fixture(text: str) -> dict[str, Any]:
    current = text.rsplit("<current_request>", 1)[-1].split("</current_request>", 1)[0]
    lower = current.strip().lower()
    knowledge_markers = (
        "document",
        "knowledge",
        "upload",
        "pdf",
        "\u6587\u6863",
        "\u77e5\u8bc6",
        "\u4e0a\u4f20",
    )
    analysis_markers = (
        "analysis",
        "analyze",
        "data",
        "query",
        "sql",
        "metric",
        "trend",
        "conversion",
        "revenue",
        "funnel",
        "visit_log",
        "turn_log",
        "telemetry_log",
        "uat",
        "session",
        "telemetry",
        "\u4f1a\u8bdd",
        "\u5206\u6790",
        "\u6570\u636e",
        "\u67e5\u8be2",
        "\u6307\u6807",
        "\u8d8b\u52bf",
        "\u8f6c\u5316",
        "\u5b8c\u6574\u6027",
        "whtr",
        "touchless",
        "foc",
        "fcr",
        "t3b",
        "\u8f6c\u4eba\u5de5",
        "\u6ee1\u610f",
    )
    metric_markers = (
        "conversion",
        "revenue",
        "orders",
        "users",
        "rate",
        "count",
        "session",
        "turn",
        "event",
        "visit",
        "\u8f6c\u5316",
        "\u6536\u5165",
        "\u8ba2\u5355",
        "\u7528\u6237",
        "\u7387",
        "\u6570\u91cf",
        "\u5b8c\u6574\u6027",
        "\u4f1a\u8bdd",
        "\u8f6e\u6b21",
        "\u4e8b\u4ef6",
        "whtr",
        "touchless",
        "foc",
        "fcr",
        "t3b",
        "\u8f6c\u4eba\u5de5",
        "\u6ee1\u610f",
    )
    time_markers = (
        "today",
        "yesterday",
        "week",
        "month",
        "quarter",
        "year",
        "last",
        "since",
        "\u4eca\u5929",
        "\u6628\u5929",
        "\u5468",
        "\u6708",
        "\u5b63\u5ea6",
        "\u5e74",
        "\u6700\u8fd1",
    )
    total_scope_markers = (
        "how many",
        "total",
        "all time",
        "\u591a\u5c11",
        "\u603b\u6570",
        "\u603b\u5171",
    )
    if any(marker in lower for marker in knowledge_markers):
        route = "knowledge"
        missing = (
            ["document"]
            if any(marker in lower for marker in ("upload", "ingest", "\u4e0a\u4f20"))
            and not any(
                ext in lower for ext in (".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md")
            )
            else []
        )
    elif any(marker in lower for marker in analysis_markers):
        route = "analysis"
        missing = []
        if not any(marker in lower for marker in metric_markers):
            missing.append("metric definition")
        if (
            not any(marker in lower for marker in time_markers)
            and not re.search(r"\b20\d{2}\b", lower)
            and not any(marker in lower for marker in total_scope_markers)
            and not any(marker in lower for marker in ("uat", "super agent"))
            and re.search(r"(?<![a-z0-9_])sa(?![a-z0-9_])", lower) is None
        ):
            missing.append("time range and timezone")
    else:
        route = "chat"
        missing = []
    return {
        "route": route,
        "task_goal": current.strip()[:500] or "Respond to the current request.",
        "missing_fields": missing,
        "decision_summary": "Mock structured goal classification.",
        "confidence": 0.9,
    }


def analysis_narrative_fixture(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    confirmed = []
    inferred = []
    for conclusion in payload.get("conclusions", []):
        item = {
            "text": str(conclusion["text"]),
            "evidence_ids": list(conclusion.get("evidence_ids", [])),
        }
        if str(conclusion.get("epistemic_label", "")).lower() == "inferred":
            inferred.append(item)
        else:
            confirmed.append(item)
    return {
        "executive_summary": payload.get("executive_summary")
        or "The approved analysis completed with evidence-linked results.",
        "confirmed_findings": confirmed,
        "inferred_findings": inferred,
        "unknowns": payload.get("unknowns", []),
        "next_actions": payload.get("recommendations", []),
        "limitations": payload.get("limitations", []),
    }


def analysis_intent_fixture(text: str) -> dict[str, Any]:
    question = (
        text.split("Conversation context:", 1)[0]
        .split("Approved semantic context:", 1)[0]
        .split("Approved catalog:", 1)[0]
    )
    lower = (
        question.removeprefix("Current question:")
        .removeprefix("Question:")
        .strip()
        .lower()
    )
    if any(
        marker in lower
        for marker in ("super agent", "uat", "visit_log", "turn_log", "telemetry_log")
    ):
        if any(
            marker in lower
            for marker in ("telemetry", "event", "\u57cb\u70b9", "\u4e8b\u4ef6")
        ):
            metric = "Super Agent UAT Telemetry Event Count"
            default_dimension = "event_name"
        elif any(
            marker in lower for marker in ("turn", "\u8f6e\u6b21", "\u5bf9\u8bdd\u8f6e")
        ):
            metric = "Super Agent UAT Turn Count"
            default_dimension = ""
        else:
            metric = "Super Agent UAT Session Count"
            default_dimension = "channel"
        if any(marker in lower for marker in ("channel", "\u6e20\u9053")):
            analysis_type, dimensions, chart_type = "segment_breakdown", ["channel"], "bar"
        elif any(marker in lower for marker in ("intent", "\u610f\u56fe")):
            analysis_type, dimensions, chart_type = (
                "segment_breakdown",
                ["intent_type"],
                "bar",
            )
        elif default_dimension and any(
            marker in lower for marker in ("breakdown", "\u5206\u7ec4", "\u7ec6\u5206")
        ):
            analysis_type, dimensions, chart_type = (
                "segment_breakdown",
                [default_dimension],
                "bar",
            )
        elif any(
            marker in lower
            for marker in ("trend", "\u8d8b\u52bf", "\u6bcf\u5929", "\u6bcf\u65e5")
        ):
            analysis_type, dimensions, chart_type = "trend", ["period"], "line"
        else:
            analysis_type, dimensions, chart_type = "trend", [], "kpi"
        result = _intent(
            analysis_type,
            metric,
            dimensions,
            ["super_agent_uat"],
            chart_type,
            "Return only bounded UAT results with auditable SQL.",
        )
        result["start_date"] = "2026-06-01"
        result["end_date"] = "2026-08-01"
        return result
    if any(marker in lower for marker in ("contribution", "stacked", "\u8d21\u732e")):
        return _intent(
            "contribution",
            "revenue",
            ["segment", "period"],
            ["sales_postgres"],
            "stacked_bar",
            "Calculate component shares and reconciliation gap.",
        )
    if any(marker in lower for marker in ("segment", "breakdown", "\u5206\u7ec4", "\u7ec6\u5206")):
        return _intent(
            "segment_breakdown",
            "revenue",
            ["segment"],
            ["sales_postgres"],
            "bar",
            "Compare bounded segment totals.",
        )
    if any(
        marker in lower
        for marker in (
            "missing",
            "duplicate",
            "completeness",
            "null",
            "\u5b8c\u6574",
            "\u7f3a\u5931",
            "\u91cd\u590d",
        )
    ):
        return _intent(
            "quality",
            "funnel completeness",
            ["stage", "period"],
            ["operations_sqlserver"],
            "table",
            "Count null and duplicate records.",
        )
    if any(
        marker in lower
        for marker in ("funnel", "conversion rate", "rate calculation", "\u6f0f\u6597", "\u8f6c\u5316\u7387")
    ):
        return _intent(
            "funnel_rate",
            "conversion rate",
            ["period"],
            ["operations_sqlserver"],
            "kpi",
            "Calculate numerator, denominator, and rate.",
        )
    if any(
        marker in lower
        for marker in ("correlation", "causal", "cause", "why", "\u76f8\u5173", "\u56e0\u679c", "\u4e3a\u4ec0\u4e48")
    ):
        return _intent(
            "correlation",
            "revenue versus marketing spend",
            ["campaign_id", "channel"],
            ["sales_postgres", "marketing_mysql"],
            "scatter",
            "Measure association and explicitly avoid causal interpretation.",
        )
    if any(marker in lower for marker in ("cross", "channel", "campaign", "\u8de8\u5e93", "\u6e20\u9053")):
        return _intent(
            "segment_breakdown",
            "revenue by channel",
            ["channel"],
            ["sales_postgres", "marketing_mysql"],
            "bar",
            "Join bounded campaign results and compare channels.",
        )
    if any(marker in lower for marker in ("anomaly", "change detection", "\u5f02\u5e38", "\u7a81\u53d8")):
        return _intent(
            "anomaly",
            "revenue",
            ["period"],
            ["sales_postgres"],
            "line",
            "Flag basic bounded z-score candidates.",
        )
    if any(marker in lower for marker in ("seasonality", "calendar", "\u5b63\u8282", "\u65e5\u5386")):
        return _intent(
            "seasonality",
            "revenue",
            ["period"],
            ["sales_postgres"],
            "line",
            "Form a calendar hypothesis with limitations.",
        )
    if any(marker in lower for marker in ("compare", "period comparison", "\u73af\u6bd4", "\u540c\u6bd4")):
        return _intent(
            "period_comparison",
            "revenue",
            ["period"],
            ["sales_postgres"],
            "bar",
            "Compare the first and last bounded periods.",
        )
    return _intent(
        "trend",
        "revenue",
        ["period"],
        ["sales_postgres"],
        "line",
        "Return a bounded revenue trend with evidence.",
    )


def _intent(
    analysis_type: str,
    metric: str,
    dimensions: list[str],
    source_ids: list[str],
    chart_type: str,
    success_criteria: str,
) -> dict[str, Any]:
    return {
        "analysis_type": analysis_type,
        "metric": metric,
        "dimensions": dimensions,
        "source_ids": source_ids,
        "start_date": "2025-01-01",
        "end_date": "2026-01-01",
        "chart_type": chart_type,
        "success_criteria": success_criteria,
        "causal_design": False,
    }
