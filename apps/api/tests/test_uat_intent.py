from __future__ import annotations

from datetime import date, timedelta

from ama_teammate.analysis.uat_intent import infer_uat_intent


def test_fast_uat_total_does_not_require_model() -> None:
    intent = infer_uat_intent("UAT \u603b\u5171\u6709\u591a\u5c11 session")
    assert intent is not None
    assert intent.metric == "Super Agent UAT Session Count"
    assert intent.chart_type.value == "kpi"
    assert intent.end_date == (date.today() + timedelta(days=1)).isoformat()


def test_current_correction_uses_prior_uat_context() -> None:
    intent = infer_uat_intent(
        "Use turn instead",
        "Earlier question: How many Super Agent UAT sessions are there?",
    )
    assert intent is not None
    assert intent.metric == "Super Agent UAT Turn Count"


def test_visit_anomaly_gets_pilot_comparison_window() -> None:
    intent = infer_uat_intent("Super Agent UAT 7/15 \u8bbf\u95ee\u91cf\u5f02\u5e38")
    assert intent is not None
    assert intent.analysis_type.value == "anomaly"
    assert intent.start_date == f"{date.today().year}-07-01"
    assert intent.end_date == f"{date.today().year}-07-16"
    assert any("14 days" in item for item in intent.assumptions)


def test_user_confirmed_whtr_is_authoritative() -> None:
    intent = infer_uat_intent("Show Super Agent UAT WHTR")
    assert intent is not None
    assert intent.metric == "WHTR"
    assert intent.metadata_confidence == "authoritative"
    assert intent.assumptions


def test_sa_alias_matches_real_whtr_phrase() -> None:
    intent = infer_uat_intent("SA\u76ee\u524dWHTR\u6574\u4f53\u662f\u591a\u5c11")
    assert intent is not None
    assert intent.metric == "WHTR"
    assert intent.metadata_confidence == "authoritative"


def test_draft_rate_respects_requested_daily_dimension() -> None:
    intent = infer_uat_intent("WHTR by day", "Super Agent UAT")
    assert intent is not None
    assert intent.analysis_type.value == "trend"
    assert intent.dimensions == ["period"]
    assert intent.chart_type.value == "line"


def test_metric_can_combine_time_and_category_dimensions() -> None:
    intent = infer_uat_intent("WHTR by day and channel", "Super Agent UAT")
    assert intent is not None
    assert intent.analysis_type.value == "trend"
    assert intent.dimensions == ["period", "channel"]
    assert intent.chart_type.value == "line"


def test_telemetry_count_can_group_by_event_name() -> None:
    intent = infer_uat_intent("UAT telemetry event count by event_name")
    assert intent is not None
    assert intent.metric == "Super Agent UAT Telemetry Event Count"
    assert intent.dimensions == ["event_name"]
    assert intent.chart_type.value == "bar"


def test_cid_session_share_uses_confirmed_field_semantics() -> None:
    intent = infer_uat_intent("能看到数据里目前cid的session占比多少吗")
    assert intent is not None
    assert intent.metric == "CID Session Rate"
    assert intent.analysis_type.value == "funnel_rate"
    assert intent.chart_type.value == "kpi"
    assert intent.metadata_confidence == "authoritative"
    assert any("is_cid=true" in item for item in intent.assumptions)


def test_case_creation_rate_daily_trend_is_not_traffic() -> None:
    intent = infer_uat_intent("case creation rate daily trend", "Super Agent UAT")
    assert intent is not None
    assert intent.metric == "Case Creation Rate"
    assert intent.metadata_confidence == "authoritative"
    assert intent.dimensions == ["period"]
    assert intent.chart_type.value == "line"


def test_user_supplied_volume_metrics_are_recognized() -> None:
    expected = {
        "transfer_volume": "Transfer Volume",
        "wh volume": "Working Hour Volume",
        "SA ticket volume": "SA Ticket Volume",
        "touchless volume": "Touchless Volume",
        "partial_touchless_volume": "Partial Touchless Volume",
        "case only volume": "Case Only Volume",
        "FOC volume": "FOC Volume",
        "survey volume": "Survey Volume",
    }
    for phrase, metric in expected.items():
        intent = infer_uat_intent(phrase, "Super Agent UAT")
        assert intent is not None
        assert intent.metric == metric


def test_dimension_only_revision_uses_latest_prior_user_metric() -> None:
    context = """<conversation_history>
[USER] WHTR overall
[ASSISTANT] Old response
[USER] case creation rate
</conversation_history>"""
    intent = infer_uat_intent("by day", context)
    assert intent is not None
    assert intent.metric == "Case Creation Rate"
    assert intent.dimensions == ["period"]


def test_uat_detail_rows_detect_table_and_limit() -> None:
    intent = infer_uat_intent("Show Super Agent UAT turn_log detail rows for user_input limit 12")
    assert intent is not None
    assert intent.analysis_type.value == "detail"
    assert intent.detail_table == "turn_log"
    assert intent.detail_limit == 12
    assert intent.chart_type.value == "table"


def test_case_journey_diagnostic_uses_three_day_baseline() -> None:
    intent = infer_uat_intent(
        "Super Agent 7\u67085\u65e5\u5efa\u5355\u91cf\u4e0b\u964d\uff0c\u770b\u770b\u7528\u6237\u79bb\u5f00\u5728\u54ea\u4e2aagent\u9636\u6bb5"
    )

    assert intent is not None
    assert intent.analysis_type.value == "journey_diagnostic"
    assert intent.start_date == f"{date.today().year}-07-02"
    assert intent.end_date == f"{date.today().year}-07-06"
    assert intent.dimensions == ["comparison_window", "exit_stage"]
    assert intent.chart_type.value == "bar"


def test_low_day_followup_reuses_case_context_for_journey_diagnostic() -> None:
    context = "<conversation_history>\n[USER] case creation rate daily trend\n[ASSISTANT] The result is available.\n</conversation_history>"
    intent = infer_uat_intent("为什么7月18日表现这么低", context)

    assert intent is not None
    assert intent.analysis_type.value == "journey_diagnostic"
    assert intent.start_date == f"{date.today().year}-07-15"
    assert intent.end_date == f"{date.today().year}-07-19"
