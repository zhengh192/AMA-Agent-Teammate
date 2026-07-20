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
    "whtr",
    "case creation",
    "touchless",
    "transfer volume",
    "ticket volume",
    "foc",
    "survey volume",
    "t3b",
    "cid",
    "is_cid",
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
_TREND_MARKERS = (
    "trend",
    "daily",
    "by day",
    "by date",
    "\u8d8b\u52bf",
    "\u6bcf\u5929",
    "\u6bcf\u65e5",
    "\u6309\u5929",
    "\u6309\u65e5",
)
_ANOMALY_MARKERS = ("anomaly", "abnormal", "\u5f02\u5e38", "\u7a81\u53d8")
_JOURNEY_DIAGNOSTIC_MARKERS = (
    "root cause",
    "rootcause",
    "drop-off",
    "drop off",
    "abandon",
    "pd down",
    "ka down",
    "case volume drop",
    "ticket volume drop",
    "\u6839\u56e0",
    "\u539f\u56e0",
    "\u4e3a\u4ec0\u4e48",
    "\u4f4e",
    "\u4e0b\u964d",
    "\u4e0b\u8dcc",
    "\u79bb\u5f00\u9636\u6bb5",
    "\u6d41\u5931\u9636\u6bb5",
    "\u6f0f\u6597\u5206\u6790",
)
_CHANNEL_MARKERS = ("channel", "\u6e20\u9053")
_INTENT_MARKERS = ("intent", "\u610f\u56fe")
_EVENT_NAME_MARKERS = ("event name", "event_name", "\u4e8b\u4ef6\u540d", "\u4e8b\u4ef6\u540d\u79f0")
_DETAIL_MARKERS = (
    "detail rows",
    "detail records",
    "row-level",
    "raw rows",
    "raw records",
    "sample rows",
    "sample records",
    "\u660e\u7ec6",
    "\u539f\u59cb\u8bb0\u5f55",
    "\u6837\u672c\u8bb0\u5f55",
    "\u6761\u8bb0\u5f55",
)


def _requested_dimensions(text: str) -> list[str]:
    dimensions: list[str] = []
    if any(marker in text for marker in _TREND_MARKERS):
        dimensions.append("period")
    if any(marker in text for marker in _CHANNEL_MARKERS):
        dimensions.append("channel")
    if any(marker in text for marker in _INTENT_MARKERS):
        dimensions.append("intent_type")
    if any(marker in text for marker in _EVENT_NAME_MARKERS):
        dimensions.append("event_name")
    return dimensions


def is_uat_reference(question: str, context: str = "") -> bool:
    combined = f"{context}\n{question}".casefold()
    return any(marker in combined for marker in _SOURCE_MARKERS) or bool(
        re.search(r"(?<![a-z0-9_])sa(?![a-z0-9_])", combined)
    )


def parse_uat_dates(text: str) -> tuple[date, date, list[str]]:
    return _dates(text.casefold())


def _detail_table(text: str) -> str | None:
    if "telemetry_log" in text or any(marker in text for marker in ("telemetry", "\u57cb\u70b9")):
        return "telemetry_log"
    if "turn_log" in text or any(marker in text for marker in ("turn", "\u8f6e\u6b21")):
        return "turn_log"
    if "visit_log" in text or any(
        marker in text for marker in ("session", "visit", "\u4f1a\u8bdd")
    ):
        return "visit_log"
    return None


def _detail_limit(text: str) -> int:
    patterns = (
        r"\blimit\s+(\d{1,3})\b",
        r"\b(?:latest|last|first|top)\s+(\d{1,3})\s+(?:rows?|records?)\b",
        r"(?<!\d)(\d{1,3})\s*\u6761(?:\u8bb0\u5f55)?",
    )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return min(max(int(matched.group(1)), 1), 200)
    return 50


def infer_uat_intent(question: str, context: str = "") -> AnalysisIntent | None:
    """Fast pilot interpretation for common UAT questions without a model round trip."""
    current = question.casefold()
    if not is_uat_reference(question, context):
        return None

    combined = f"{context}\n{question}".casefold()
    if _is_journey_diagnostic(current, combined):
        start_date, end_date, time_assumptions = _journey_diagnostic_dates(current)
        return AnalysisIntent(
            analysis_type=AnalysisKind.JOURNEY_DIAGNOSTIC,
            metric="Case Journey Stage Diagnostic",
            dimensions=["comparison_window", "exit_stage"],
            source_ids=["super_agent_uat"],
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            chart_type=ChartKind.BAR,
            success_criteria=(
                "Compare case success and failed-session exit-stage distributions before "
                "and during the incident, with evidence and explicit unknowns."
            ),
            metadata_confidence="working_assumption",
            assumptions=[
                "The working eligible cohort requires visit_log.intent_type='hardware' and pd_triggered='yes'.",
                "A session is successful when eticket_case_number or msd_case_number is present.",
                "Failure stage uses the last hardware or flow-related turn, not the physical last turn.",
                "Stage concentration localizes the failure path but does not prove the system root cause.",
                *time_assumptions,
            ],
        )
    if any(marker in current for marker in _DETAIL_MARKERS):
        start_date, end_date, time_assumptions = _dates(current)
        return AnalysisIntent(
            analysis_type=AnalysisKind.DETAIL,
            metric="Super Agent UAT Detail Rows",
            dimensions=[],
            source_ids=["super_agent_uat"],
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            chart_type=ChartKind.TABLE,
            success_criteria=(
                "Return explicitly selected, bounded detail rows after SQL approval."
            ),
            assumptions=[
                "UAT identifier and text fields are encrypted or tokenized before storage.",
                "Detail output remains subject to the configured row and byte limits.",
                *time_assumptions,
            ],
            detail_table=_detail_table(current) or _detail_table(combined),
            detail_limit=_detail_limit(current),
        )

    metric, confidence, metric_assumptions = _metric(current)
    if metric is None and any(
        marker in current for marker in (*_TREND_MARKERS, *_CHANNEL_MARKERS, *_INTENT_MARKERS)
    ):
        prior_user_messages = re.findall(r"\[USER\]\s*(.+)", context, flags=re.IGNORECASE)
        for prior_message in reversed(prior_user_messages):
            metric, confidence, metric_assumptions = _metric(prior_message.casefold())
            if metric is not None:
                break
    if metric is None:
        return None
    start_date, end_date, time_assumptions = _dates(current)
    assumptions = [*metric_assumptions, *time_assumptions]

    dimensions = _requested_dimensions(current)
    if any(marker in current for marker in _ANOMALY_MARKERS):
        if "period" not in dimensions:
            dimensions.insert(0, "period")
        kind, chart = AnalysisKind.ANOMALY, ChartKind.LINE
    elif "period" in dimensions:
        kind, chart = AnalysisKind.TREND, ChartKind.LINE
    elif dimensions:
        kind, chart = AnalysisKind.SEGMENT_BREAKDOWN, ChartKind.BAR
    elif confidence == "working_assumption" or metric == "CID Session Rate":
        kind, chart = AnalysisKind.FUNNEL_RATE, ChartKind.KPI
    elif any(marker in current for marker in _TOTAL_MARKERS):
        kind, chart = AnalysisKind.TREND, ChartKind.KPI
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


def _is_journey_diagnostic(current: str, combined: str) -> bool:
    diagnostic_requested = any(marker in current for marker in _JOURNEY_DIAGNOSTIC_MARKERS)
    journey_subject = any(
        marker in combined
        for marker in (
            "case",
            "ticket",
            "pd",
            "ka",
            "hardware",
            "\u5efa\u5355",
            "\u7ef4\u4fee\u5355",
            "\u786c\u4ef6",
        )
    )
    return diagnostic_requested and journey_subject


def _journey_diagnostic_dates(text: str) -> tuple[date, date, list[str]]:
    parsed = _explicit_dates(text)
    incident_date = parsed[-1] if parsed else date.today() - timedelta(days=1)
    baseline_start = parsed[0] if len(parsed) >= 2 else incident_date - timedelta(days=3)
    if baseline_start >= incident_date:
        baseline_start = incident_date - timedelta(days=3)
    return (
        baseline_start,
        incident_date + timedelta(days=1),
        [
            f"Incident calendar date is {incident_date.isoformat()}.",
            f"Baseline starts {baseline_start.isoformat()} and ends before the incident date.",
            "Database timezone remains unknown.",
        ],
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
        "by",
        "name",
        "event_name",
        "\u6309",
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
    if ("cid" in text or "is_cid" in text) and any(
        marker in text for marker in ("session", "rate", "ratio", "share", "占比", "比例", "率")
    ):
        return (
            "CID Session Rate",
            "authoritative",
            [
                "Confirmed by the user on 2026-07-17: logical is_cid=true maps to physical value '1'.",
                "The denominator is all non-null visit_log session rows in the bounded interval.",
            ],
        )
    taught_sql_assumptions = [
        "Confirmed UAT working definition supplied by the user on 2026-07-17; row grain is visit_log rows.",
        "The supplied definition excludes rows where channel is null.",
    ]
    taught_metrics = (
        (
            (
                "case creation rate",
                "case_creation_rate",
                "case create rate",
                "\u5efa\u5355\u7387",
                "\u5efacase\u7387",
            ),
            "Case Creation Rate",
        ),
        (
            (
                "transfer volume",
                "transfer_volume",
                "\u8f6c\u4eba\u5de5\u91cf",
                "\u8f6c\u4eba\u5de5\u6570\u91cf",
            ),
            "Transfer Volume",
        ),
        (
            ("working hour volume", "wh volume", "wh_volume", "\u5de5\u4f5c\u65f6\u95f4\u91cf"),
            "Working Hour Volume",
        ),
        (
            ("sa ticket volume", "sa_ticket_volume", "ticket volume", "\u5efa\u5355\u91cf"),
            "SA Ticket Volume",
        ),
        (
            ("partial touchless volume", "partial_touchless_volume", "\u90e8\u5206touchless\u91cf"),
            "Partial Touchless Volume",
        ),
        (("touchless volume", "touchless_volume", "touchless\u91cf"), "Touchless Volume"),
        (
            ("case only volume", "case_only_volume", "cased volume", "\u4ec5\u5efa\u5355\u91cf"),
            "Case Only Volume",
        ),
        (("foc volume", "foc_volume", "foc\u91cf"), "FOC Volume"),
        (("survey volume", "survey_volume", "\u95ee\u5377\u91cf", "survey\u91cf"), "Survey Volume"),
    )
    for aliases, name in taught_metrics:
        if any(alias in text for alias in aliases):
            return name, "authoritative", taught_sql_assumptions
    if _is_simple_count(text, ("telemetry", "event", "events", "\u57cb\u70b9", "\u4e8b\u4ef6")):
        return "Super Agent UAT Telemetry Event Count", "authoritative", []
    if _is_simple_count(text, ("turn", "turns", "\u8f6e\u6b21", "\u5bf9\u8bdd\u8f6e")):
        return "Super Agent UAT Turn Count", "authoritative", []
    if any(
        marker in text
        for marker in ("partial touchless", "\u90e8\u5206\u65e0\u4eba", "\u90e8\u5206\u81ea\u52a8")
    ):
        return (
            "Partial Touchless Rate",
            "working_assumption",
            ["Draft 930 rate definition remains separate from the confirmed volume definition."],
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
        return "Touchless Rate", "authoritative", taught_sql_assumptions
    if any(
        marker in text
        for marker in (
            "whtr",
            "working hours transfer",
            "\u5de5\u4f5c\u65f6\u95f4\u8f6c\u4eba\u5de5",
            "\u8f6c\u4eba\u5de5\u7387",
        )
    ):
        return "WHTR", "authoritative", taught_sql_assumptions
    if any(
        marker in text
        for marker in ("t3b", "survey satisfaction", "\u6ee1\u610f\u7387", "\u6ee1\u610f\u5ea6")
    ):
        return "T3B Rate", "authoritative", taught_sql_assumptions
    if any(
        marker in text
        for marker in ("fcr", "first contact resolution", "\u9996\u6b21\u89e3\u51b3\u7387")
    ):
        return (
            "FCR",
            "working_assumption",
            ["Draft 930 formula uses survey_resolved; repeat-contact window is unknown."],
        )
    if any(
        marker in text
        for marker in ("foc", "fixed on contact", "\u5f53\u524d\u4f1a\u8bdd\u89e3\u51b3")
    ):
        return (
            "FOC Rate",
            "working_assumption",
            ["FOC rate was not defined in the supplied SQL; only FOC volume was confirmed."],
        )
    if _is_simple_count(
        text, ("session", "sessions", "visit", "visits", "\u8bbf\u95ee\u91cf", "\u4f1a\u8bdd")
    ):
        return "Super Agent UAT Session Count", "authoritative", taught_sql_assumptions
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
        for start_month, start_day, end_month, end_day in re.findall(
            r"(?<!\d)(\d{1,2})(\d{2})\s*[-~\u81f3\u5230]\s*(\d{1,2})(\d{2})(?!\d)",
            text,
        ):
            parsed.extend(
                (
                    date(today.year, int(start_month), int(start_day)),
                    date(today.year, int(end_month), int(end_day)),
                )
            )

        for month, day in re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text):
            parsed.append(date(today.year, int(month), int(day)))
    if not parsed:
        for month, day in re.findall(r"(?<!\d)(\d{1,2})\u6708(\d{1,2})\u65e5?", text):
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


def _explicit_dates(text: str) -> list[date]:
    today = date.today()
    parsed: list[date] = []
    for year, month, day in re.findall(
        r"\b(20\d{2})[-/\u5e74](\d{1,2})[-/\u6708](\d{1,2})(?:\u65e5)?\b",
        text,
    ):
        parsed.append(date(int(year), int(month), int(day)))
    if not parsed:
        for start_month, start_day, end_month, end_day in re.findall(
            r"(?<!\d)(\d{1,2})(\d{2})\s*[-~\u81f3\u5230]\s*(\d{1,2})(\d{2})(?!\d)",
            text,
        ):
            parsed.extend(
                (
                    date(today.year, int(start_month), int(start_day)),
                    date(today.year, int(end_month), int(end_day)),
                )
            )

    if not parsed:
        for month, day in re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text):
            parsed.append(date(today.year, int(month), int(day)))
    if not parsed:
        for month, day in re.findall(r"(?<!\d)(\d{1,2})\u6708(\d{1,2})\u65e5?", text):
            parsed.append(date(today.year, int(month), int(day)))
    return parsed
