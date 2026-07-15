from __future__ import annotations

from typing import Any


def analysis_intent_fixture(text: str) -> dict[str, Any]:
    question = text.split("Approved catalog:", 1)[0]
    lower = question.removeprefix("Question:").strip().lower()
    if any(marker in lower for marker in ("contribution", "stacked", "贡献", "堆叠")):
        return _intent(
            "contribution",
            "revenue",
            ["segment", "period"],
            ["sales_postgres"],
            "stacked_bar",
            "Calculate component shares and reconciliation gap.",
        )
    if any(marker in lower for marker in ("segment", "breakdown", "分组", "细分")):
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
        for marker in ("missing", "duplicate", "completeness", "null", "完整", "缺失", "重复")
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
        for marker in ("funnel", "conversion rate", "rate calculation", "漏斗", "转化率")
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
        for marker in ("correlation", "causal", "cause", "why", "相关", "因果", "为什么")
    ):
        return _intent(
            "correlation",
            "revenue versus marketing spend",
            ["campaign_id", "channel"],
            ["sales_postgres", "marketing_mysql"],
            "scatter",
            "Measure association and explicitly avoid causal interpretation.",
        )
    if any(marker in lower for marker in ("cross", "channel", "campaign", "跨库", "渠道")):
        return _intent(
            "segment_breakdown",
            "revenue by channel",
            ["channel"],
            ["sales_postgres", "marketing_mysql"],
            "bar",
            "Join bounded campaign results and compare channels.",
        )
    if any(marker in lower for marker in ("anomaly", "change detection", "异常", "突变")):
        return _intent(
            "anomaly",
            "revenue",
            ["period"],
            ["sales_postgres"],
            "line",
            "Flag basic bounded z-score candidates.",
        )
    if any(marker in lower for marker in ("seasonality", "calendar", "季节", "日历")):
        return _intent(
            "seasonality",
            "revenue",
            ["period"],
            ["sales_postgres"],
            "line",
            "Form a calendar hypothesis with limitations.",
        )
    if any(marker in lower for marker in ("compare", "period comparison", "环比", "同比")):
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
