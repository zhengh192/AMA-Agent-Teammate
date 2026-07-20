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

ROOT = Path(__file__).resolve().parents[3]


def _dataset() -> Dataset:
    rows = [
        {"comparison_window": "baseline", "exit_stage": "CASE_CREATED", "value": 30},
        {
            "comparison_window": "baseline",
            "exit_stage": "HARDWARE_BEFORE_KA_FLOW",
            "value": 40,
        },
        {"comparison_window": "baseline", "exit_stage": "KA_FLOW_C1", "value": 30},
        {"comparison_window": "incident", "exit_stage": "CASE_CREATED", "value": 10},
        {
            "comparison_window": "incident",
            "exit_stage": "HARDWARE_BEFORE_KA_FLOW",
            "value": 20,
        },
        {"comparison_window": "incident", "exit_stage": "KA_FLOW_C1", "value": 70},
    ]
    return Dataset(
        id="case-journey-dataset",
        source_ids=["super_agent_uat"],
        columns=["comparison_window", "exit_stage", "value"],
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
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.JOURNEY_DIAGNOSTIC,
        metric="Case Journey Stage Diagnostic",
        dimensions=["comparison_window", "exit_stage"],
        source_ids=["super_agent_uat"],
        start_date="2026-07-02",
        end_date="2026-07-06",
        chart_type=ChartKind.BAR,
        success_criteria="Locate the changed journey stage before reviewing themes.",
    )

    computation = ControlledAnalysisEngine().analyze(intent, _dataset(), None)

    assert computation.summary["windows"]["baseline"]["success_rate"] == 0.3
    assert computation.summary["windows"]["incident"]["success_rate"] == 0.1
    assert computation.summary["success_rate_change"] == pytest.approx(-0.2)
    assert computation.summary["largest_share_increase_stage"] == "KA_FLOW_C1"
    assert computation.summary["next_layer"] == "bounded_response_theme_review"
    assert any(item.epistemic_label == "Unknown" for item in computation.conclusions)


def test_journey_diagnostic_skill_is_active_and_in_execution_plan() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")

    assert issues == []
    package = registry.get("case_journey_diagnostics")
    assert package.metadata.status == SkillStatus.ACTIVE
    execution_plan = registry.build_execution_plan(
        AnalysisKind.JOURNEY_DIAGNOSTIC, "Why did case volume drop on July 5?"
    )
    assert any(step.skill.id == "case_journey_diagnostics" for step in execution_plan)
