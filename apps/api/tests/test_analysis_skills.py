from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ama_teammate.analysis.charts import recommend_chart
from ama_teammate.analysis.models import AnalysisKind, ChartKind
from ama_teammate.analysis.quality import assess_dataset_quality
from ama_teammate.analysis_skills.calculations import (
    calculate_change,
    calculate_funnel,
    calculate_match_rate,
    calculate_referential_integrity,
    check_freshness,
    check_nulls_and_duplicates,
    check_period_coverage,
    check_schema_consistency,
    check_volume_anomaly,
    decompose_mix_rate,
    small_sample_warning,
)
from ama_teammate.analysis_skills.evaluator import (
    load_evaluation_suite,
    run_evaluation_suite,
)
from ama_teammate.analysis_skills.models import SkillMetadata, SkillStatus
from ama_teammate.analysis_skills.registry import (
    AnalysisSkillRegistry,
    AnalysisSkillValidationError,
)
from ama_teammate.config import Settings
from ama_teammate.main import create_app

ROOT = Path(__file__).resolve().parents[3]


def _parse_sse(lines: Iterator[str]) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event = "message"
    for line in lines:
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event, json.loads(line.removeprefix("data: "))))
    return events


def test_foundation_registry_validates_active_skills_and_strict_schema() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")
    assert issues == []
    assert len(registry.list_packages(SkillStatus.ACTIVE)) == 10
    raw = yaml.safe_load((ROOT / "skills/metric_query/metadata.yaml").read_text(encoding="utf-8"))
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        SkillMetadata.model_validate(raw)


def test_invalid_prerequisite_is_rejected(tmp_path: Path) -> None:
    source = ROOT / "skills/analysis_reporting"
    target = tmp_path / "analysis_reporting"
    target.mkdir()
    (target / "SKILL.md").write_text(
        (source / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    metadata = yaml.safe_load((source / "metadata.yaml").read_text(encoding="utf-8"))
    metadata["prerequisite_skills"] = ["missing_skill"]
    (target / "metadata.yaml").write_text(
        yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
    )
    _, issues = AnalysisSkillRegistry.load(tmp_path)
    assert any(issue.code == "invalid_prerequisite" and issue.active for issue in issues)


def _invalid_active_skill(root: Path) -> None:
    target = root / "broken_skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Broken\n\nInvalid active package.", encoding="utf-8")
    (target / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "broken_skill",
                "version": "1.0.0",
                "status": "active",
            }
        ),
        encoding="utf-8",
    )


def test_development_startup_fails_for_invalid_active_skill(
    settings: Settings, tmp_path: Path
) -> None:
    root = tmp_path / "invalid-skills"
    _invalid_active_skill(root)
    invalid_settings = settings.model_copy(update={"ama_analysis_skill_root": root})
    with pytest.raises(AnalysisSkillValidationError), TestClient(create_app(invalid_settings)):
        pass


def test_production_rejects_invalid_skill_and_emits_audit(
    settings: Settings, tmp_path: Path
) -> None:
    root = tmp_path / "invalid-production-skills"
    _invalid_active_skill(root)
    production = settings.model_copy(
        update={"ama_env": "production", "ama_analysis_skill_root": root}
    )
    with TestClient(create_app(production)) as production_client:
        assert production_client.get("/api/analysis-skills").json() == []
        database_path = Path(production.ama_metadata_database_url.split("///", 1)[1])
        with sqlite3.connect(database_path) as connection:
            event_type = connection.execute(
                "SELECT event_type FROM audit_events WHERE event_type = ?",
                ("analysis_skill.definition.rejected",),
            ).fetchone()
        assert event_type == ("analysis_skill.definition.rejected",)


def test_skill_api_lists_retrieves_and_searches(client: TestClient) -> None:
    listed = client.get("/api/analysis-skills", params={"status": "active"})
    assert listed.status_code == 200
    assert len(listed.json()) == 10
    retrieved = client.get("/api/analysis-skills/mix_rate_decomposition")
    assert retrieved.status_code == 200
    assert retrieved.json()["version"] == "1.0.0"
    assert "instructions" in retrieved.json()
    searched = client.get("/api/analysis-skills/search", params={"q": "漏斗转化"})
    assert searched.status_code == 200
    assert searched.json()[0]["id"] == "funnel_analysis"


def test_analysis_plan_retrieves_metadata_then_skills_before_sql(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    planner = client.app.state.analysis_service.planner
    events: list[str] = []
    original_list = planner.semantic_registry.list_definitions
    original_generate = planner.providers.provider.generate_structured
    original_skills = planner.skill_registry.build_execution_plan
    original_validate = planner.gateway.validate

    def tracked_list(*args: Any, **kwargs: Any) -> Any:
        events.append("metadata")
        return original_list(*args, **kwargs)

    async def tracked_generate(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request") or (args[2] if len(args) > 2 else None)
        if getattr(request, "name", None) == "analysis_intent":
            events.append("intent")
        return await original_generate(*args, **kwargs)

    def tracked_skills(*args: Any, **kwargs: Any) -> Any:
        events.append("skills")
        return original_skills(*args, **kwargs)

    def tracked_validate(*args: Any, **kwargs: Any) -> Any:
        events.append("sql")
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(planner.semantic_registry, "list_definitions", tracked_list)
    monkeypatch.setattr(planner.providers.provider, "generate_structured", tracked_generate)
    monkeypatch.setattr(planner.skill_registry, "build_execution_plan", tracked_skills)
    monkeypatch.setattr(planner.gateway, "validate", tracked_validate)

    session = client.post("/api/sessions", json={"title": "skill order"}).json()
    with client.stream(
        "POST",
        f"/api/sessions/{session['id']}/messages/stream",
        json={"content": "Query revenue trend for 2025 from PostgreSQL."},
    ) as response:
        assert response.status_code == 200
        sse = _parse_sse(response.iter_lines())
    approval = next(data for name, data in sse if name == "approval.required")
    assert (
        events.index("metadata")
        < events.index("intent")
        < events.index("skills")
        < events.index("sql")
    )
    skill_ids = [step["skill"]["id"] for step in approval["plan"]["skill_execution_plan"]]
    assert skill_ids == [
        "metric_query",
        "data_quality_check",
        "trend_anomaly_analysis",
        "analysis_reporting",
    ]
    with client.stream(
        "POST",
        f"/api/runs/{approval['run_id']}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": approval["payload_hash"],
            "status": "approved",
        },
    ) as response:
        assert response.status_code == 200
        completed = _parse_sse(response.iter_lines())
    result = next(data for name, data in completed if name == "analysis.result")
    assert [item["id"] for item in result["skill_references"]] == skill_ids
    assert all(item["version"] == "1.0.0" for item in result["skill_references"])
    trace = client.get(f"/api/runs/{approval['run_id']}/trace").json()
    resolved = next(item for item in trace if item["event_type"] == "semantic_metadata.resolved")
    assert [
        item["skill"]["id"] for item in resolved["safe_details"]["skill_execution_plan"]
    ] == skill_ids
    assert all(
        item["skill"]["version"] == "1.0.0"
        for item in resolved["safe_details"]["skill_execution_plan"]
    )


def test_deterministic_calculations_and_data_confidence() -> None:
    change = calculate_change(0.1, 0.12, is_rate=True)
    assert change.percentage_point_change == pytest.approx(2)
    assert change.relative_change == pytest.approx(0.2)
    funnel = calculate_funnel(100, 60)
    assert funnel.conversion_rate == 0.6
    assert funnel.drop_off_rate == 0.4
    match = calculate_match_rate([1, 2, 3, 4], [1, 2, 3])
    assert match.match_rate == 0.75
    assert small_sample_warning(5) is not None
    rows = [{"id": 1, "value": None}, {"id": 1, "value": None}]
    check = check_nulls_and_duplicates(rows)
    assert check.duplicate_rows == 1
    assert check.null_rates["value"] == 1
    assert check_freshness(None, 60).fresh is None
    quality = assess_dataset_quality(rows, ["id", "value"])
    assert quality.confidence.value in {"low", "unusable"}

    assert check_volume_anomaly(10, 100)
    assert check_schema_consistency({"id"}, {"id", "value"})["missing_columns"] == ["value"]
    assert calculate_referential_integrity([1, 2, 3], [1, 2]) == pytest.approx(2 / 3)
    assert check_period_coverage(["2025-01"], ["2025-01", "2025-02"]) == {
        "complete": False,
        "missing_periods": ["2025-02"],
    }
    assert recommend_chart(AnalysisKind.TREND, 1) is None
    assert recommend_chart(AnalysisKind.MIX_RATE_DECOMPOSITION, 2) == ChartKind.WATERFALL


def test_mix_rate_decomposition_reconciles() -> None:
    result = decompose_mix_rate(
        {"A": 0.5, "B": 0.5},
        {"A": 0.2, "B": 0.4},
        {"A": 0.25, "B": 0.75},
        {"A": 0.3, "B": 0.5},
    )
    assert result.total_change == pytest.approx(
        result.mix_effect + result.rate_effect + result.interaction_effect
    )
    assert result.reconciliation_gap == pytest.approx(0)


def test_all_25_evaluation_cases_assert_expected_behavior() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")
    assert issues == []
    suite = load_evaluation_suite(ROOT / "evals/generic_cases.yaml")
    counts = Counter(case.category for case in suite.cases)
    assert counts == {
        "metric_query": 4,
        "period_comparison": 4,
        "trend_anomaly": 4,
        "contribution": 4,
        "mix_rate": 3,
        "funnel": 2,
        "cross_source": 2,
        "ambiguous": 2,
    }
    results = run_evaluation_suite(suite, registry)
    assert len(results) == 25
    assert [result for result in results if not result.passed] == []


def test_admin_analysis_skill_edit_approval_hot_reload_and_deprecation(
    settings: Settings, tmp_path: Path
) -> None:
    skill_root = tmp_path / "managed-analysis-skills"
    shutil.copytree(ROOT / "skills", skill_root)
    isolated = settings.model_copy(
        update={
            "ama_analysis_skill_root": skill_root,
            "ama_skill_registry_root": tmp_path / "taught-skills",
        }
    )
    with TestClient(create_app(isolated)) as managed_client:
        detail = managed_client.get("/api/analysis-skills/mix_rate_decomposition").json()
        old_version = detail["version"]
        instructions = detail.pop("instructions") + "\n\nKeep every contribution reconciled.\n"
        detail.pop("path")
        detail["description"] = detail["description"] + " Admin-reviewed."
        proposal_response = managed_client.post(
            "/api/analysis-skills/proposals",
            json={"metadata": detail, "instructions": instructions},
        )
        assert proposal_response.status_code == 200, proposal_response.text
        proposal = proposal_response.json()
        assert proposal["proposal_type"] == "analysis_skill"
        assert proposal["base_version"] == old_version
        assert (
            managed_client.get("/api/analysis-skills/mix_rate_decomposition").json()["version"]
            == old_version
        )

        wrong = managed_client.post(
            f"/api/skills/proposals/{proposal['id']}/decision",
            json={"decision": "approved", "payload_hash": "0" * 64},
        )
        assert wrong.status_code == 400
        approved = managed_client.post(
            f"/api/skills/proposals/{proposal['id']}/decision",
            json={"decision": "approved", "payload_hash": proposal["payload_hash"]},
        )
        assert approved.status_code == 200, approved.text
        current = managed_client.get("/api/analysis-skills/mix_rate_decomposition").json()
        assert current["version"] != old_version
        assert current["description"].endswith("Admin-reviewed.")
        assert "Keep every contribution reconciled." in current["instructions"]
        assert (
            managed_client.app.state.analysis_service.planner.skill_registry.get(
                "mix_rate_decomposition"
            ).metadata.version
            == current["version"]
        )

        deprecation_metadata = {
            key: value for key, value in current.items() if key not in {"path", "instructions"}
        }
        deprecation_metadata["status"] = "deprecated"
        deprecation = managed_client.post(
            "/api/analysis-skills/proposals",
            json={
                "metadata": deprecation_metadata,
                "instructions": current["instructions"],
            },
        ).json()
        retired = managed_client.post(
            f"/api/skills/proposals/{deprecation['id']}/decision",
            json={"decision": "approved", "payload_hash": deprecation["payload_hash"]},
        )
        assert retired.status_code == 200, retired.text
        assert (
            managed_client.get("/api/analysis-skills/mix_rate_decomposition").json()["status"]
            == "deprecated"
        )
        active_ids = {
            item["id"]
            for item in managed_client.get(
                "/api/analysis-skills", params={"status": "active"}
            ).json()
        }
        assert "mix_rate_decomposition" not in active_ids
