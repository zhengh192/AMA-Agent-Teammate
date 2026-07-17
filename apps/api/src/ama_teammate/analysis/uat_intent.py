from __future__ import annotations

import re
from datetime import date, timedelta

from ama_teammate.analysis.models import AnalysisIntent, AnalysisKind, ChartKind

_SOURCE_MARKERS = (
    "super agent",
    "uat",
    "visit_log",
    "turn_log",
    "telemetry_log",
    "\u8bbf\u95ee\u91cf",
)
_TOTAL_MARKERS = (
    "how many",
    "total",
    "all time",
    "\u591a\u5c11",
    "\u603b\u6570",
    "\u603b\u5171",
    "\u603b\u5171\u6709",
)
_TREND_MARKERS = ("trend", "daily", "by day", "\u8d8b\u52bf", "\u6bcf\u5929", "\u6bcf\u65e5")
_ANOMALY_MARKERS = ("anomaly", "abnormal", "\u5f02\u5e38", "\u7a81\u53d8")
_CHANNEL_MARKERS = ("channel", "\u6e20\u9053")
_INTENT_MARKERS = ("intent", "\u610f\u56fe")


def is_uat_reference(question: str, context: str = "") -> bool:
    combined = f"{context}\n{question}".casefold()
    return any(marker in combined for marker in _SOURCE_MARKERS) or bool(
        re.search(r"(?<![a-z0-9_])sa(?![a-z0-9_])", combined)
    )


def parse_uat_dates(text: str) -> tuple[date, date, list[str]]:
    return _dates(text.casefold())


def infer_uat_intent(question: str, context: str = "") -> AnalysisIntent | None:
    """Fast pilot interpretation for common UAT questions without a model round trip."""
    current = question.casefold()
    if not is_uat_reference(question, context):
        return None

    metric, confidence, metric_assumptions = _metric(current)
    if metric is None:
        return None
    start_date, end_date, time_assumptions = _dates(current)
    assumptions = [*metric_assumptions, *time_assumptions]

    if confidence == "working_assumption":
        kind, dimensions, chart = AnalysisKind.FUNNEL_RATE, [], ChartKind.KPI
    elif any(marker in current for marker in _CHANNEL_MARKERS):
        kind, dimensions, chart = AnalysisKind.SEGMENT_BREAKDOWN, ["channel"], ChartKind.BAR
    elif any(marker in current for marker in _INTENT_MARKERS):
        kind, dimensions, chart = AnalysisKind.SEGMENT_BREAKDOWN, ["intent_type"], ChartKind.BAR
    elif any(marker in current for marker in _ANOMALY_MARKERS):
        kind, dimensions, chart = AnalysisKind.ANOMALY, ["period"], ChartKind.LINE
    elif any(marker in current for marker in _TREND_MARKERS):
        kind, dimensions, chart = AnalysisKind.TREND, ["period"], ChartKind.LINE
    elif any(marker in current for marker in _TOTAL_MARKERS):
        kind, dimensions, chart = AnalysisKind.TREND, [], ChartKind.KPI
    else:
        kind, dimensions, chart = AnalysisKind.TREND, ["period"], ChartKind.LINE

    return AnalysisIntent(
        analysis_type=kind,
        metric=metric,
        dimensions=dimensions,
        source_ids=["super_agent_uat"],
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        chart_type=chart,
        success_criteria=(
            "Return a bounded result with SQL, evidence, and explicit working assumptions."
        ),
        metadata_confidence=confidence,
        assumptions=assumptions,
    )


def _is_simple_count(text: str, subject_terms: tuple[str, ...]) -> bool:
    if not any(term in text for term in subject_terms):
        return False
    remainder = text
    removable = (
        *subject_terms,
        "super agent",
        "uat",
        "sa",
        "how many",
        "total",
        "all time",
        "count",
        "there are",
        "are there",
        "current",
        "currently",
        "overall",
        "in",
        "use",
        "show",
        "instead",
        "trend",
        "daily",
        "by day",
        "anomaly",
        "abnormal",
        "\u591a\u5c11",
        "\u603b\u6570",
        "\u603b\u5171",
        "\u603b\u5171\u6709",
        "\u76ee\u524d",
        "\u5f53\u524d",
        "\u6574\u4f53",
        "\u73b0\u5728",
        "\u662f\u591a\u5c11",
        "\u6709",
        "\u7684",
        "\u4e2a",
        "\u8d8b\u52bf",
        "\u6bcf\u5929",
        "\u6bcf\u65e5",
        "\u5f02\u5e38",
        "\u7a81\u53d8",
    )
    for item in sorted(removable, key=len, reverse=True):
        remainder = remainder.replace(item, " ")
    remainder = re.sub(r"\b20\d{2}(?:[-/]\d{1,2}){0,2}\b", " ", remainder)
    remainder = re.sub(r"(?<!\d)\d{1,2}/\d{1,2}(?!\d)", " ", remainder)
    remainder = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", remainder)
    return not remainder


def _metric(text: str) -> tuple[str | None, str, list[str]]:
    if _is_simple_count(text, ("telemetry", "event", "events", "\u57cb\u70b9", "\u4e8b\u4ef6")):
        return "Super Agent UAT Telemetry Event Count", "authoritative", []
    if _is_simple_count(text, ("turn", "turns", "\u8f6e\u6b21", "\u5bf9\u8bdd\u8f6e")):
        return "Super Agent UAT Turn Count", "authoritative", []
    if any(
        marker in text
        for marker in (
            "partial touchless",
            "\u90e8\u5206\u65e0\u4eba\u5de5",
            "\u90e8\u5206\u81ea\u52a8",
        )
    ):
        return (
            "Partial Touchless Rate",
            "working_assumption",
            [
                "Draft 930 definition; session grain is used because the case identity model is open."
            ],
        )
    if any(
        marker in text
        for marker in (
            "touchless",
            "\u5168\u81ea\u52a8",
            "\u65e0\u4eba\u5904\u7406",
            "\u65e0\u4eba\u5de5",
        )
    ):
        return (
            "Touchless Rate",
            "working_assumption",
            [
                "Draft 930 definition; session grain is used because the case identity model is open."
            ],
        )
    if any(
        marker in text
        for marker in (
            "whtr",
            "working hours transfer",
            "\u5de5\u4f5c\u65f6\u95f4\u8f6c\u4eba\u5de5",
            "\u8f6c\u4eba\u5de5\u7387",
        )
    ):
        return (
            "WHTR",
            "working_assumption",
            [
                "Draft 930 formula; working-hour eligibility and transfer flag values need confirmation."
            ],
        )
    if any(
        marker in text
        for marker in ("t3b", "survey satisfaction", "\u6ee1\u610f\u7387", "\u6ee1\u610f\u5ea6")
    ):
        return (
            "T3B Rate",
            "working_assumption",
            ["Draft 930 formula uses submitted survey scores >= 8; survey coverage is low."],
        )
    if any(
        marker in text
        for marker in ("fcr", "first contact resolution", "\u9996\u6b21\u89e3\u51b3\u7387")
    ):
        return (
            "FCR",
            "working_assumption",
            [
                "Draft 930 formula uses the survey_resolved response; repeat-contact window is unknown."
            ],
        )
    if any(
        marker in text
        for marker in ("foc", "fixed on contact", "\u5f53\u524d\u4f1a\u8bdd\u89e3\u51b3")
    ):
        return (
            "FOC Rate",
            "working_assumption",
            [
                "Draft 930 formula uses the physical is_foc flag and all observed sessions as denominator."
            ],
        )
    if _is_simple_count(
        text, ("session", "sessions", "visit", "visits", "\u8bbf\u95ee\u91cf", "\u4f1a\u8bdd")
    ):
        return "Super Agent UAT Session Count", "authoritative", []
    return None, "authoritative", []


def _dates(text: str) -> tuple[date, date, list[str]]:
    today = date.today()
    parsed: list[date] = []
    for year, month, day in re.findall(
        r"\b(20\d{2})[-/\u5e74](\d{1,2})[-/\u6708](\d{1,2})(?:\u65e5)?\b",
        text,
    ):
        parsed.append(date(int(year), int(month), int(day)))
    if not parsed:
        for month, day in re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text):
            parsed.append(date(today.year, int(month), int(day)))

    if len(parsed) >= 2:
        return (
            parsed[0],
            parsed[1] + timedelta(days=1),
            ["Date range is treated as inclusive and timezone remains unknown."],
        )
    if parsed:
        target = parsed[0]
        if any(marker in text for marker in _ANOMALY_MARKERS):
            return (
                target - timedelta(days=14),
                target + timedelta(days=1),
                [
                    f"Anomaly check uses the 14 days ending {target.isoformat()} as a pilot comparison window.",
                    "Timezone remains unknown.",
                ],
            )
        return (
            target,
            target + timedelta(days=1),
            ["The stated date is treated as one calendar day; timezone remains unknown."],
        )
    return (
        date(2026, 6, 1),
        today + timedelta(days=1),
        [
            "No date was supplied; the current UAT observed window is used and timezone remains unknown."
        ],
    )
