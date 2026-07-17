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


def test_draft_kpi_is_labeled_working_assumption() -> None:
    intent = infer_uat_intent("Show Super Agent UAT WHTR")
    assert intent is not None
    assert intent.metric == "WHTR"
    assert intent.metadata_confidence == "working_assumption"
    assert intent.assumptions
def test_sa_alias_matches_real_whtr_phrase() -> None:
    intent = infer_uat_intent("SA\u76ee\u524dWHTR\u6574\u4f53\u662f\u591a\u5c11")
    assert intent is not None
    assert intent.metric == "WHTR"
    assert intent.metadata_confidence == "working_assumption"
