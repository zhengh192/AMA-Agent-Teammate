from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SkillId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
SemanticVersion = Annotated[
    str, StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SkillRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LocalizedTriggerExamples(StrictModel):
    en: list[str] = Field(min_length=1, max_length=12)
    zh: list[str] = Field(min_length=1, max_length=12)


class SkillInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["string", "number", "boolean", "date", "dataset", "metric", "period", "evidence"]
    required: bool = True
    description: str = Field(min_length=1, max_length=500)


class SkillOutput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["number", "table", "chart", "evidence", "analysis_result", "quality_report", "dataset"]
    description: str = Field(min_length=1, max_length=500)


class ApprovalSettings(StrictModel):
    required: bool
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_reason(self) -> ApprovalSettings:
        if self.required and not self.reason:
            raise ValueError("Approval reason is required when approval is enabled.")
        return self


class DiagnosticHierarchyLevel(StrictModel):
    key: Literal["agent_stage", "symptom", "flow_step"]
    label_en: str = Field(min_length=1, max_length=80)
    label_zh: str = Field(min_length=1, max_length=80)


class JourneyDiagnosticContract(StrictModel):
    baseline_aggregation: Literal["daily_average"] = "daily_average"
    rank_by: Literal["excess_failed_sessions", "failure_share_change"] = (
        "excess_failed_sessions"
    )
    hierarchy: list[DiagnosticHierarchyLevel] = Field(min_length=1, max_length=3)
    show_top_n: int = Field(default=5, ge=1, le=20)
    small_sample_threshold: int = Field(default=5, ge=1, le=100)
    drill_down_only_positive_parent: bool = True
    evidence_style: Literal["numbered_labels"] = "numbered_labels"
    output_language: Literal["match_user"] = "match_user"

    @model_validator(mode="after")
    def require_unique_hierarchy(self) -> JourneyDiagnosticContract:
        keys = [item.key for item in self.hierarchy]
        if len(keys) != len(set(keys)):
            raise ValueError("Journey diagnostic hierarchy levels must be unique.")
        return self


class SkillMetadata(StrictModel):
    id: SkillId
    name: str = Field(min_length=3, max_length=120)
    version: SemanticVersion
    status: SkillStatus
    description: str = Field(min_length=10, max_length=1_000)
    owner: str = Field(min_length=2, max_length=120)
    reviewer: str = Field(min_length=2, max_length=120)
    created_at: datetime
    updated_at: datetime
    effective_from: date
    effective_to: date | None = None
    aliases: list[str] = Field(default_factory=list, max_length=20)
    trigger_examples: LocalizedTriggerExamples
    analysis_intents: list[str] = Field(min_length=1, max_length=12)
    required_metadata: list[Literal["metric", "dataset", "field", "relationship", "business_rule"]]
    prerequisite_skills: list[SkillId] = Field(default_factory=list, max_length=8)
    inputs: list[SkillInput] = Field(min_length=1, max_length=20)
    outputs: list[SkillOutput] = Field(min_length=1, max_length=20)
    required_tools: list[str] = Field(default_factory=list, max_length=20)
    deterministic_operations: list[str] = Field(default_factory=list, max_length=20)
    risk_level: SkillRiskLevel
    approval: ApprovalSettings
    journey_diagnostic_contract: JourneyDiagnosticContract | None = None

    @model_validator(mode="after")
    def validate_dates_and_references(self) -> SkillMetadata:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at.")
        if self.id in self.prerequisite_skills:
            raise ValueError("A skill cannot depend on itself.")
        return self


class SkillReference(StrictModel):
    id: SkillId
    version: SemanticVersion


class SkillExecutionStep(StrictModel):
    order: int = Field(ge=1)
    skill: SkillReference
    reason: str = Field(min_length=1, max_length=500)
    prerequisite_skills: list[SkillReference] = Field(default_factory=list)
    required_metadata: list[str] = Field(default_factory=list)
    deterministic_operations: list[str] = Field(default_factory=list)
    approval_required: bool


class SkillPackage(StrictModel):
    metadata: SkillMetadata
    instructions: str = Field(min_length=20)
    path: str


class SkillValidationIssue(StrictModel):
    path: str
    code: str
    message: str
    skill_id: str | None = None
    version: str | None = None
    active: bool = False

    def safe_details(self) -> dict[str, str | bool | None]:
        return self.model_dump()
