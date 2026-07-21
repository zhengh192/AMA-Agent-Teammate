from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ama_teammate.analysis.agent_loop import BoundedAnalysisLoop
from ama_teammate.analysis.models import AnalysisKind, AnalysisTaskKind
from ama_teammate.analysis.python_sandbox import (
    DisabledPythonSandbox,
    DockerPythonSandbox,
    PythonSandboxRequest,
    PythonSandboxUnavailable,
)
from ama_teammate.analysis.task_understanding import TaskUnderstandingService
from ama_teammate.analysis_skills.models import SkillStatus
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry
from ama_teammate.config import Settings
from ama_teammate.orchestration.nodes import build_assess_goal_node
from ama_teammate.orchestration.state import AgentState
from ama_teammate.providers.base import ModelProfile
from ama_teammate.providers.factory import ProviderBundle, create_provider_bundle

ROOT = Path(__file__).resolve().parents[3]


class SemanticTaskProvider:
    name = "azure"

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, *_args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        request = kwargs.get("request") or _args[2]
        if request.name == "goal_assessment":
            return request.schema.model_validate(
                {
                    "route": "chat",
                    "task_goal": "Investigate the incident conversationally.",
                    "decision_summary": "Model assessed the outcome.",
                    "missing_fields": [],
                    "task_steps": [],
                }
            )
        return request.schema.model_validate(
            {
                "task_kind": "diagnose",
                "user_goal": "Model-created incident plan.",
                "subject": "Model-selected subject",
                "is_follow_up": False,
                "needs_clarification": False,
                "investigation_steps": [
                    {
                        "order": 1,
                        "name": "Establish baseline",
                        "objective": "Compare the incident with a recent baseline.",
                        "completion_signal": "The change is quantified.",
                    }
                ],
                "preferred_tools": ["sql", "controlled_analysis"],
            }
        )


class ContinueReviewProvider:
    name = "azure"

    async def generate_structured(self, *_args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request") or _args[2]
        return request.schema.model_validate(
            {
                "decision": "continue",
                "observation": "The baseline moved, but the largest stage shift is not localized.",
                "completed_plan_step": "Quantified the incident against baseline.",
                "next_question": (
                    "Compare failed-session share by agent stage between the incident and baseline."
                ),
                "learning_candidates": [],
            }
        )


@pytest.mark.asyncio
async def test_goal_routing_uses_model_even_when_fallback_would_choose_chat() -> None:
    provider = SemanticTaskProvider()
    profile = ModelProfile(name="test", deployment="test")
    bundle = ProviderBundle(
        provider=provider,  # type: ignore[arg-type]
        coordinator=profile,
        analyst=profile,
        curator=profile,
    )

    result = await build_assess_goal_node(bundle)(
        AgentState(
            schema_version="2",
            session_id="session",
            run_id="run",
            user_id="user",
            input_text="Please help me investigate this incident.",
            combined_input="Please help me investigate this incident.",
            status="created",
        )
    )

    assert provider.calls == 1
    assert result["decision_summary"] != "Intent-first deterministic routing fallback."


@pytest.mark.asyncio
async def test_task_understanding_uses_model_before_case_specific_fallback() -> None:
    provider = SemanticTaskProvider()
    profile = ModelProfile(name="test", deployment="test")
    service = TaskUnderstandingService(
        ProviderBundle(
            provider=provider,  # type: ignore[arg-type]
            coordinator=profile,
            analyst=profile,
            curator=profile,
        )
    )

    result = await service.understand(
        "Why was case creation rate low on July 11?",
        "",
        [],
    )

    assert provider.calls == 1
    assert result is not None
    assert result.subject == "Model-selected subject"
    assert result.investigation_steps[0].name == "Establish baseline"


def test_content_matched_skill_can_extend_static_intent_plan() -> None:
    registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")
    assert not [item for item in issues if item.active]

    plan = registry.build_execution_plan(
        AnalysisKind.DETAIL,
        "Use Case Journey Diagnostics to inspect failed sessions.",
    )

    assert "case_journey_diagnostics" in [item.skill.id for item in plan]
    assert all(
        registry.get(item.skill.id, item.skill.version).metadata.status == SkillStatus.ACTIVE
        for item in plan
    )


@pytest.mark.asyncio
async def test_bounded_loop_stops_at_iteration_limit() -> None:
    providers = create_provider_bundle(Settings(_env_file=None, ama_provider="mock"))
    loop = BoundedAnalysisLoop(providers, max_iterations=1)
    plan = SimpleNamespace(
        goal="Diagnose the change",
        intent=SimpleNamespace(
            task_kind=AnalysisTaskKind.DIAGNOSE,
            investigation_steps=[],
            analysis_type=AnalysisKind.ANOMALY,
        ),
    )
    step = SimpleNamespace(
        iteration=1,
        datasets=[SimpleNamespace()],
        computation=SimpleNamespace(evidence=[SimpleNamespace()]),
    )

    review = await loop.review(
        original_question="Why did it change?",
        plan=plan,  # type: ignore[arg-type]
        step=step,  # type: ignore[arg-type]
        prior_observations=[],
        skill_methods=[],
    )

    assert review.decision == "finish"
    assert "Iteration 1" in review.observation


@pytest.mark.asyncio
async def test_bounded_loop_uses_model_to_choose_the_next_analytical_step() -> None:
    profile = ModelProfile(name="test", deployment="test")
    loop = BoundedAnalysisLoop(
        ProviderBundle(
            provider=ContinueReviewProvider(),  # type: ignore[arg-type]
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        max_iterations=3,
    )
    quality = SimpleNamespace(model_dump=lambda **_kwargs: {"confidence": "high"})
    dataset = SimpleNamespace(
        id="dataset-1",
        columns=["comparison_window", "stage", "value"],
        rows=[{"comparison_window": "incident", "stage": "KA", "value": 12}],
        row_count=1,
        quality=quality,
    )
    plan = SimpleNamespace(
        goal="Diagnose the case-creation decline",
        intent=SimpleNamespace(
            task_kind=AnalysisTaskKind.DIAGNOSE,
            user_goal="Find where failed sessions increased.",
            investigation_steps=[],
            analysis_type=AnalysisKind.ANOMALY,
            metric="Case Creation Rate",
            dimensions=[],
        ),
    )
    step = SimpleNamespace(
        iteration=1,
        final_dataset_id="dataset-1",
        datasets=[dataset],
        computation=SimpleNamespace(summary="The rate declined.", conclusions=[]),
    )

    review = await loop.review(
        original_question="Why did case creation decline?",
        plan=plan,  # type: ignore[arg-type]
        step=step,  # type: ignore[arg-type]
        prior_observations=[],
        skill_methods=[],
    )

    assert review.decision == "continue"
    assert review.next_question is not None
    assert "agent stage" in review.next_question


@pytest.mark.asyncio
async def test_disabled_python_sandbox_never_executes_in_api_process() -> None:
    with pytest.raises(PythonSandboxUnavailable, match="disabled"):
        await DisabledPythonSandbox().execute(PythonSandboxRequest(code="result = {}", datasets={}))


@pytest.mark.asyncio
async def test_docker_python_sandbox_uses_no_network_and_read_only_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b'AMA_RESULT={"rows": [{"value": 1}]}\n', b""

        def kill(self) -> None:
            return None

    async def fake_subprocess(*args: str, **_kwargs: Any) -> FakeProcess:
        captured.extend(args)
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    result = await DockerPythonSandbox(image="python:3.12.4-slim").execute(
        PythonSandboxRequest(
            code="result = {'rows': datasets['input']}",
            datasets={"input": [{"value": 1}]},
        )
    )

    assert result.output["rows"] == [{"value": 1}]
    assert captured[captured.index("--network") + 1] == "none"
    assert "--read-only" in captured
    assert "--cap-drop" in captured
    mount = captured[captured.index("--mount") + 1]
    assert mount.endswith(",readonly")
