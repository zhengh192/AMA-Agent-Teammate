from __future__ import annotations

import json
from typing import Any

from ama_teammate.analysis.models import (
    AnalysisTaskKind,
    AnalysisTaskUnderstanding,
    InvestigationStep,
)
from ama_teammate.providers.base import ProviderMessage, StructuredProviderRequest
from ama_teammate.providers.factory import ProviderBundle

TASK_UNDERSTANDING_INSTRUCTIONS = """Interpret the user's analytical outcome before choosing a
query or chart. Return only the supplied structured task frame. Use the current request together
with the latest relevant conversation turn. A request asking why a metric is bad, low, degraded,
abnormal, or changed is a diagnosis, not merely a trend chart. A diagnosis must preserve the named
metric and incident date, establish the change against a baseline, localize contributing segments
or journey stages, and only then inspect deeper evidence. A chart is an output format, never the
task goal. Do not generate SQL, answer the question, expose chain-of-thought, invent fields, or
claim that data was queried. Approved Skill instructions are executable operating guidance, not
background prose: use them to propose bounded investigation_steps and return their IDs in
recommended_skill_ids. Never select an unavailable Skill ID. Ask for clarification only when the
intended outcome or incident is materially ambiguous."""


class TaskUnderstandingService:
    def __init__(self, providers: ProviderBundle) -> None:
        self.providers = providers

    async def understand(
        self,
        question: str,
        context: str,
        skill_context: list[dict[str, Any]],
    ) -> AnalysisTaskUnderstanding | None:
        deterministic = _case_diagnostic_frame(question, context)
        if deterministic is not None:
            return deterministic
        if self.providers.provider.name == "mock" or not _needs_semantic_framing(question, context):
            return None
        generated = await self.providers.provider.generate_structured(
            [
                ProviderMessage(role="developer", content=TASK_UNDERSTANDING_INSTRUCTIONS),
                ProviderMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "current_request": question,
                            "recent_conversation": context[-6_000:],
                            "available_skills": skill_context,
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            self.providers.analyst,
            StructuredProviderRequest(
                name="analysis_task_understanding",
                schema=AnalysisTaskUnderstanding,
            ),
        )
        if not isinstance(generated, AnalysisTaskUnderstanding):
            raise TypeError("Provider returned an invalid analysis task understanding")
        return generated


def _needs_semantic_framing(question: str, context: str) -> bool:
    current = question.casefold()
    recent = context[-3_000:].casefold()
    diagnostic_markers = (
        "why",
        "reason",
        "root cause",
        "bad",
        "poor",
        "low",
        "lower",
        "drop",
        "decrease",
        "degraded",
        "abnormal",
        "unexpected",
        "investigate",
        "diagnose",
        "\u4e3a\u4ec0\u4e48",
        "\u539f\u56e0",
        "\u6839\u56e0",
        "\u4e0b\u964d",
        "\u504f\u4f4e",
        "\u5f02\u5e38",
        "\u8bca\u65ad",
    )
    if any(marker in current for marker in diagnostic_markers):
        return True
    return "abnormal" in current and any(
        marker in recent for marker in ("why", "reason", "\u4e3a\u4ec0\u4e48", "\u539f\u56e0")
    )


def _case_diagnostic_frame(question: str, context: str) -> AnalysisTaskUnderstanding | None:
    current = question.casefold()
    recent = context[-3_000:].casefold()
    subject_markers = ("case creation", "case rate", "ticket volume", "\u5efa\u5355")
    diagnostic_markers = (
        "why",
        "reason",
        "bad",
        "poor",
        "low",
        "drop",
        "decrease",
        "degraded",
        "abnormal",
        "unexpected",
        "\u4e3a\u4ec0\u4e48",
        "\u539f\u56e0",
        "\u4e0b\u964d",
        "\u504f\u4f4e",
        "\u5f02\u5e38",
    )
    subject_is_case = any(marker in f"{recent}\n{current}" for marker in subject_markers)
    asks_for_diagnosis = any(marker in current for marker in diagnostic_markers)
    if not subject_is_case or not asks_for_diagnosis:
        return None
    chinese = any("\u4e00" <= character <= "\u9fff" for character in question)
    return AnalysisTaskUnderstanding(
        task_kind=AnalysisTaskKind.DIAGNOSE,
        user_goal=(
            "\u5148\u91cf\u5316\u5efa\u5355\u7387\u4e0e\u57fa\u7ebf\u7684\u53d8\u5316\uff0c\u518d\u6309 Agent \u9636\u6bb5\u3001\u75c7\u72b6\u548c\u6b65\u9aa4\u9010\u5c42\u5b9a\u4f4d\u5931\u8d25\u589e\u91cf\uff0c"
            "\u6700\u540e\u518d\u68c0\u67e5\u9650\u5b9a\u8303\u56f4\u7684\u5931\u8d25\u8bdd\u672f\u3002"
            if chinese
            else (
                "Diagnose the case-creation incident by measuring the change against a recent "
                "baseline, then localizing excess failures through Agent stage, symptom, and "
                "flow step before reviewing bounded response evidence."
            )
        ),
        subject="Case Creation Rate",
        is_follow_up=bool(context.strip()),
        investigation_steps=[
            InvestigationStep(
                order=1,
                name="Verify the incident",
                objective="Quantify the case-creation change against a recent baseline.",
                completion_signal="The incident magnitude and direction are measured.",
            ),
            InvestigationStep(
                order=2,
                name="Localize the Agent stage",
                objective="Compare every failed-session Agent-stage bucket with its baseline.",
                completion_signal="The largest excess-failure Agent stage is quantified.",
            ),
            InvestigationStep(
                order=3,
                name="Drill into symptom",
                objective="Within the selected stage, compare symptom distributions when coverage supports it.",
                completion_signal="The abnormal symptom branch is quantified or explicitly unavailable.",
            ),
            InvestigationStep(
                order=4,
                name="Drill into flow step",
                objective="Within the selected symptom, compare flow-step distributions when coverage supports it.",
                completion_signal="The abnormal step is quantified or explicitly unavailable.",
            ),
            InvestigationStep(
                order=5,
                name="Inspect response evidence",
                objective="Review bounded incident and baseline bot-response samples for the localized branch.",
                completion_signal="Observed response evidence is available for a human diagnosis.",
            ),
        ],
        recommended_skill_ids=["case_journey_diagnostics"],
    )
