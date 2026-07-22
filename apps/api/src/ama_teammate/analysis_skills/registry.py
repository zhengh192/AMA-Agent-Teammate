from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ama_teammate.analysis.models import AnalysisKind
from ama_teammate.analysis_skills.models import (
    SkillExecutionStep,
    SkillMetadata,
    SkillPackage,
    SkillReference,
    SkillStatus,
    SkillValidationIssue,
)


class AnalysisSkillValidationError(ValueError):
    def __init__(self, issues: list[SkillValidationIssue]) -> None:
        self.issues = issues
        super().__init__(
            "Analysis skill validation failed: " + "; ".join(i.message for i in issues)
        )


class AnalysisSkillRegistry:
    def __init__(self, packages: list[SkillPackage]) -> None:
        self._packages = packages
        self._by_id: dict[str, list[SkillPackage]] = defaultdict(list)
        for package in packages:
            self._by_id[package.metadata.id].append(package)

    @classmethod
    def load(cls, root: Path) -> tuple[AnalysisSkillRegistry, list[SkillValidationIssue]]:
        packages: list[SkillPackage] = []
        issues: list[SkillValidationIssue] = []
        if not root.exists():
            return cls([]), [
                SkillValidationIssue(
                    path=str(root),
                    code="root_missing",
                    message="Analysis skill root is missing.",
                    active=True,
                )
            ]
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            metadata_path = directory / "metadata.yaml"
            skill_path = directory / "SKILL.md"
            if not metadata_path.exists() and not skill_path.exists():
                continue
            raw: Any = None
            try:
                raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
                metadata = SkillMetadata.model_validate(raw)
                instructions = skill_path.read_text(encoding="utf-8")
                packages.append(
                    SkillPackage(metadata=metadata, instructions=instructions, path=str(directory))
                )
            except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
                raw_status = raw.get("status") if isinstance(raw, dict) else None
                issues.append(
                    SkillValidationIssue(
                        path=str(directory.relative_to(root)),
                        code="skill_invalid",
                        message=str(exc).splitlines()[0][:500],
                        skill_id=raw.get("id") if isinstance(raw, dict) else None,
                        version=raw.get("version") if isinstance(raw, dict) else None,
                        active=raw_status == SkillStatus.ACTIVE.value,
                    )
                )
        registry = cls(packages)
        issues.extend(registry._reference_issues())
        return registry, issues

    def list_packages(self, status: SkillStatus | None = None) -> list[SkillPackage]:
        values = self._packages
        if status is not None:
            values = [item for item in values if item.metadata.status == status]
        return sorted(values, key=lambda item: (item.metadata.id, item.metadata.version))

    def validate_replacement(self, package: SkillPackage) -> list[SkillValidationIssue]:
        candidate = AnalysisSkillRegistry(
            [item for item in self._packages if item.metadata.id != package.metadata.id] + [package]
        )
        return candidate._reference_issues()

    def replace(self, package: SkillPackage) -> None:
        issues = [item for item in self.validate_replacement(package) if item.active]
        if issues:
            raise AnalysisSkillValidationError(issues)
        self._packages = [
            item for item in self._packages if item.metadata.id != package.metadata.id
        ] + [package]
        self._by_id = defaultdict(list)
        for item in self._packages:
            self._by_id[item.metadata.id].append(item)

    def get(self, skill_id: str, version: str | None = None) -> SkillPackage:
        matches = [
            item
            for item in self._by_id.get(skill_id, [])
            if version is None or item.metadata.version == version
        ]
        if version is None:
            active = [item for item in matches if self._effective(item.metadata)]
            matches = active or matches
        if not matches:
            raise LookupError(f"Analysis skill not found: {skill_id}")
        return sorted(matches, key=lambda item: _semver(item.metadata.version))[-1]

    def search(self, query: str, status: SkillStatus | None = None) -> list[SkillPackage]:
        tokens = _tokens(query)
        results: list[tuple[int, SkillPackage]] = []
        for package in self.list_packages(status):
            metadata = package.metadata
            haystack = " ".join(
                [
                    metadata.id,
                    metadata.name,
                    metadata.description,
                    *metadata.aliases,
                    *metadata.trigger_examples.en,
                    *metadata.trigger_examples.zh,
                ]
            ).lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                results.append((score, package))
        return [
            item for _, item in sorted(results, key=lambda pair: (-pair[0], pair[1].metadata.id))
        ]

    def runtime_context(
        self, question: str, *, limit: int = 6, include_instructions: bool = False
    ) -> list[dict[str, Any]]:
        selected: list[SkillPackage] = []
        for package in self.search(question, SkillStatus.ACTIVE):
            if package not in selected:
                selected.append(package)
        for skill_id in (
            "metric_query",
            "data_quality_check",
            "analysis_reporting",
        ):
            try:
                package = self.get(skill_id)
            except LookupError:
                continue
            if self._effective(package.metadata) and package not in selected:
                selected.append(package)
        return [
            {
                "id": package.metadata.id,
                "name": package.metadata.name,
                "version": package.metadata.version,
                "description": package.metadata.description,
                "aliases": package.metadata.aliases,
                "trigger_examples": package.metadata.trigger_examples.model_dump(),
                "analysis_intents": package.metadata.analysis_intents,
                "inputs": [item.model_dump(mode="json") for item in package.metadata.inputs],
                "outputs": [item.model_dump(mode="json") for item in package.metadata.outputs],
                "deterministic_operations": package.metadata.deterministic_operations,
                **({"instructions": package.instructions[:12_000]} if include_instructions else {}),
            }
            for package in selected[:limit]
        ]

    def build_execution_plan(
        self,
        analysis_kind: AnalysisKind,
        question: str,
        recommended_skill_ids: list[str] | None = None,
    ) -> list[SkillExecutionStep]:
        target_ids = _INTENT_SKILLS[analysis_kind]
        candidates = [item.metadata.id for item in self.search(question, SkillStatus.ACTIVE)]
        ordered_ids: list[str] = []

        def add_with_prerequisites(skill_id: str) -> None:
            try:
                package = self.get(skill_id)
            except LookupError:
                return
            if not self._effective(package.metadata):
                return
            for prerequisite in package.metadata.prerequisite_skills:
                add_with_prerequisites(prerequisite)
            if skill_id not in ordered_ids:
                ordered_ids.append(skill_id)

        for skill_id in target_ids:
            add_with_prerequisites(skill_id)
        for skill_id in candidates:
            if skill_id in target_ids:
                add_with_prerequisites(skill_id)
        for skill_id in self._explicitly_named_skill_ids(question):
            add_with_prerequisites(skill_id)
        for skill_id in recommended_skill_ids or []:
            add_with_prerequisites(skill_id)
        return [
            SkillExecutionStep(
                order=index,
                skill=SkillReference(id=package.metadata.id, version=package.metadata.version),
                reason=f"Required for {analysis_kind.value} analysis.",
                prerequisite_skills=[
                    SkillReference(
                        id=prerequisite,
                        version=self.get(prerequisite).metadata.version,
                    )
                    for prerequisite in package.metadata.prerequisite_skills
                ],
                required_metadata=list(package.metadata.required_metadata),
                deterministic_operations=package.metadata.deterministic_operations,
                approval_required=package.metadata.approval.required,
            )
            for index, skill_id in enumerate(ordered_ids, 1)
            for package in [self.get(skill_id)]
        ]

    def _explicitly_named_skill_ids(self, question: str) -> list[str]:
        normalized_question = _normalized_phrase(question)
        matched: list[str] = []
        for package in self.list_packages(SkillStatus.ACTIVE):
            metadata = package.metadata
            names = [metadata.id.replace("_", " "), metadata.name, *metadata.aliases]
            if any(
                (normalized := _normalized_phrase(name))
                and len(normalized) >= 4
                and normalized in normalized_question
                for name in names
            ):
                matched.append(metadata.id)
        return matched

    def _reference_issues(self) -> list[SkillValidationIssue]:
        issues: list[SkillValidationIssue] = []
        active_by_id: dict[str, list[SkillPackage]] = defaultdict(list)
        for package in self._packages:
            if self._effective(package.metadata):
                active_by_id[package.metadata.id].append(package)
        for skill_id, packages in active_by_id.items():
            if len(packages) > 1:
                issues.append(
                    SkillValidationIssue(
                        path=skill_id,
                        code="duplicate_active_skill",
                        message=f"Duplicate active skill ID: {skill_id}",
                        skill_id=skill_id,
                        active=True,
                    )
                )
        for package in self._packages:
            if not self._effective(package.metadata):
                continue
            for prerequisite in package.metadata.prerequisite_skills:
                if prerequisite not in active_by_id:
                    issues.append(
                        SkillValidationIssue(
                            path=package.path,
                            code="invalid_prerequisite",
                            message=f"Active prerequisite is missing: {prerequisite}",
                            skill_id=package.metadata.id,
                            version=package.metadata.version,
                            active=True,
                        )
                    )
        return issues

    @staticmethod
    def _effective(metadata: SkillMetadata) -> bool:
        today = date.today()
        return (
            metadata.status == SkillStatus.ACTIVE
            and metadata.effective_from <= today
            and (metadata.effective_to is None or metadata.effective_to >= today)
        )


_INTENT_SKILLS: dict[AnalysisKind, list[str]] = {
    AnalysisKind.DETAIL: ["data_quality_check", "analysis_reporting"],
    AnalysisKind.TREND: [
        "data_quality_check",
        "metric_query",
        "trend_anomaly_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.PERIOD_COMPARISON: [
        "data_quality_check",
        "metric_query",
        "period_comparison",
        "analysis_reporting",
    ],
    AnalysisKind.SEGMENT_BREAKDOWN: [
        "data_quality_check",
        "metric_query",
        "contribution_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.CONTRIBUTION: [
        "data_quality_check",
        "metric_query",
        "contribution_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.FUNNEL_RATE: [
        "data_quality_check",
        "metric_query",
        "funnel_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.QUALITY: ["data_quality_check", "analysis_reporting"],
    AnalysisKind.ANOMALY: [
        "data_quality_check",
        "metric_query",
        "trend_anomaly_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.SEASONALITY: [
        "data_quality_check",
        "metric_query",
        "trend_anomaly_analysis",
        "analysis_reporting",
    ],
    AnalysisKind.CORRELATION: [
        "data_quality_check",
        "metric_query",
        "cross_source_reconciliation",
        "analysis_reporting",
    ],
    AnalysisKind.MIX_RATE_DECOMPOSITION: [
        "data_quality_check",
        "metric_query",
        "mix_rate_decomposition",
        "analysis_reporting",
    ],
    AnalysisKind.CROSS_SOURCE_RECONCILIATION: [
        "data_quality_check",
        "metric_query",
        "cross_source_reconciliation",
        "analysis_reporting",
    ],
    AnalysisKind.JOURNEY_DIAGNOSTIC: [
        "data_quality_check",
        "metric_query",
        "funnel_analysis",
        "trend_anomaly_analysis",
        "case_journey_diagnostics",
        "analysis_reporting",
    ],
}


def _semver(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _normalized_phrase(value: str) -> str:
    return " ".join(
        "".join(character.lower() if character.isalnum() else " " for character in value).split()
    )


def _tokens(value: str) -> set[str]:
    normalized = _normalized_phrase(value)
    return {token for token in normalized.split() if len(token) > 1} | {
        character for character in value if "\u4e00" <= character <= "\u9fff"
    }
