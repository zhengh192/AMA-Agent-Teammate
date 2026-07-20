from __future__ import annotations

from pathlib import Path

import pytest

from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.models import (
    AnalysisIntent,
    AnalysisKind,
    ChartKind,
    DataConfidence,
    Dataset,
    DatasetQuality,
)
from ama_teammate.analysis_skills.models import SkillStatus
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry
from ama_teammate.evidence.validator import EvidenceValidator

ROOT = Path(__file__).resolve().parents[3]


def _dataset() -> Dataset:
    common = {
        "comparison_date": "2026-07-04",
        "symptom": "NO_POWER",
        "flow_step": "C1",
    }
    rows = [
        {**common, "comparison_window": "baseline", "outcome": "CASE_CREATED", "agent_stage": "CASE_CREATED", "value": 30},
        {**common, "comparison_window": "baseline", "outcome": "FAILED", "agent_stage": "MAIN", "value": 40},
        {**common, "comparison_window": "baseline", "outcome": "FAILED", "agent_stage": "KA", "value": 30},
        {**common, "comparison_date": "2026-07-05", "comparison_window": "incident", "outcome": "CASE_CREATED", "agent_stage": "CASE_CREATED", "value": 10},
        {**common, "comparison_date": "2026-07-05", "comparison_window": "incident", "outcome": "FAILED", "agent_stage": "MAIN", "value": 20},
        {**common, "comparison_date": "2026-07-05", "comparison_window": "incident", "outcome": "FAILED", "agent_stage": "KA", "value": 70},
    ]
    return Dataset(
        id="case-journey-dataset",
        source_ids=["super_agent_uat"],
        columns=[
            "comparison_date",
            "comparison_window",
            "outcome",
            "agent_stage",
            "symptom",
            "flow_step",
            "value",
        ],
        rows=rows,
        row_count=len(rows),
        result_bytes=1_000,
        quality=DatasetQuality(
            confidence=DataConfidence.HIGH,
            row_count=len(rows),
            missing_by_column={},
            duplicate_rows=0,
            warnings=[],
        ),
        query_proposal_ids=["case-journey-query"],
    )


def test_journey_diagnostic_compares_stage_distribution_without_claiming_cause() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")
    assert issues == []
    contract = registry.get("case_journey_diagnostics").metadata.journey_diagnostic_contract
    assert contract is not None
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.JOURNEY_DIAGNOSTIC,
        metric="Case Journey Stage Diagnostic",
        dimensions=["comparison_window", "agent_stage", "symptom", "flow_step"],
        source_ids=["super_agent_uat"],
        start_date="2026-07-02",
        end_date="2026-07-06",
        chart_type=ChartKind.BAR,
        success_criteria="Locate the changed journey stage before reviewing themes.",
        response_language="zh-CN",
        journey_diagnostic_contract=contract,
    )

    computation = ControlledAnalysisEngine().analyze(intent, _dataset(), None)

    assert computation.summary["windows"]["baseline"]["success_rate"] == 0.3
    assert computation.summary["windows"]["incident"]["success_rate"] == 0.1
    assert computation.summary["success_rate_change"] == pytest.approx(-0.2)
    assert computation.summary["largest_share_increase_stage"] == "KA"
    assert computation.summary["next_layer"] == "bounded_response_theme_review"
    assert [item["key"] for item in computation.summary["hierarchy"]] == [
        "agent_stage",
        "symptom",
        "flow_step",
    ]
    stage_rows = computation.summary["hierarchy"][0]["rows"]
    ka = next(item for item in stage_rows if item["value"] == "KA")
    assert ka["incident_average_daily_count"] == 70
    assert ka["baseline_average_daily_count"] == 30
    assert ka["excess_failed_sessions"] == 40
    assert computation.summary["hierarchy"][1]["selected"] == "NO_POWER"
    assert computation.summary["hierarchy"][2]["selected"] == "C1"
    assert any(item.epistemic_label == "Unknown" for item in computation.conclusions)
    EvidenceValidator().validate(computation)


def test_journey_diagnostic_skill_is_active_and_in_execution_plan() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")

    assert issues == []
    package = registry.get("case_journey_diagnostics")
    assert package.metadata.status == SkillStatus.ACTIVE
    assert package.metadata.version == "1.1.0"
    contract = package.metadata.journey_diagnostic_contract
    assert contract is not None
    assert [level.key for level in contract.hierarchy] == [
        "agent_stage",
        "symptom",
        "flow_step",
    ]
    execution_plan = registry.build_execution_plan(
        AnalysisKind.JOURNEY_DIAGNOSTIC, "Why did case volume drop on July 5?"
    )
    assert any(step.skill.id == "case_journey_diagnostics" for step in execution_plan)