from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ama_teammate.analysis.models import AnalysisKind
from ama_teammate.analysis_skills.calculations import (
    calculate_change,
    calculate_contributions,
    calculate_funnel,
    calculate_match_rate,
    decompose_mix_rate,
    reconciliation_gap,
    small_sample_warning,
)
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    category: Literal[
        "metric_query",
        "period_comparison",
        "trend_anomaly",
        "contribution",
        "mix_rate",
        "funnel",
        "cross_source",
        "ambiguous",
    ]
    operation: Literal[
        "skill_plan",
        "change",
        "small_sample",
        "contribution",
        "mix_rate",
        "funnel",
        "match_rate",
        "clarification",
    ]
    input: dict[str, Any]
    expected: dict[str, Any]


class EvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[EvaluationCase] = Field(min_length=25, max_length=25)


class EvaluationResult(BaseModel):
    case_id: str
    passed: bool
    detail: str


def load_evaluation_suite(path: Path) -> EvaluationSuite:
    return EvaluationSuite.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def run_evaluation_suite(
    suite: EvaluationSuite, registry: AnalysisSkillRegistry
) -> list[EvaluationResult]:
    return [_evaluate(case, registry) for case in suite.cases]


def _evaluate(case: EvaluationCase, registry: AnalysisSkillRegistry) -> EvaluationResult:
    try:
        actual = _execute(case, registry)
        for key, expected in case.expected.items():
            value = actual.get(key)
            if isinstance(expected, float) and isinstance(value, (int, float)):
                if abs(float(value) - expected) > 1e-9:
                    raise AssertionError(f"{key}: expected {expected}, got {value}")
            elif value != expected:
                raise AssertionError(f"{key}: expected {expected!r}, got {value!r}")
        return EvaluationResult(case_id=case.id, passed=True, detail="assertions passed")
    except Exception as exc:  # evaluation boundary records an assertion-safe failure
        return EvaluationResult(case_id=case.id, passed=False, detail=str(exc)[:500])


def _execute(case: EvaluationCase, registry: AnalysisSkillRegistry) -> dict[str, Any]:
    values = case.input
    if case.operation == "skill_plan":
        plan = registry.build_execution_plan(
            AnalysisKind(str(values["analysis_kind"])), str(values.get("question", "analysis"))
        )
        return {
            "contains_skill": str(case.expected["contains_skill"])
            if str(case.expected["contains_skill"]) in {item.skill.id for item in plan}
            else None,
            "prerequisites_resolved": all(
                prerequisite.id in {previous.skill.id for previous in plan[: index - 1]}
                for index, step in enumerate(plan, 1)
                for prerequisite in step.prerequisite_skills
            ),
        }
    if case.operation == "change":
        return calculate_change(
            float(values["previous"]), float(values["current"]), is_rate=bool(values.get("is_rate"))
        ).model_dump()
    if case.operation == "small_sample":
        return {"warning": small_sample_warning(int(values["sample_size"])) is not None}
    if case.operation == "contribution":
        changes = {key: float(value) for key, value in dict(values["changes"]).items()}
        shares = calculate_contributions(changes)
        return {
            "share_sum": sum(value for value in shares.values() if value is not None),
            "reconciliation_gap": reconciliation_gap(sum(changes.values()), list(changes.values())),
        }
    if case.operation == "mix_rate":
        return decompose_mix_rate(
            dict(values["previous_weights"]),
            dict(values["previous_rates"]),
            dict(values["current_weights"]),
            dict(values["current_rates"]),
        ).model_dump()
    if case.operation == "funnel":
        return calculate_funnel(float(values["entered"]), float(values["completed"])).model_dump()
    if case.operation == "match_rate":
        return calculate_match_rate(list(values["left_keys"]), list(values["right_keys"])).model_dump()
    if case.operation == "clarification":
        return {"clarification_required": bool(values.get("missing_or_ambiguous"))}
    raise ValueError(f"Unsupported evaluation operation: {case.operation}")
