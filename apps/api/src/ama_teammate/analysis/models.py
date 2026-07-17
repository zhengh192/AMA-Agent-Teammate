from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ama_teammate.analysis_skills.models import SkillExecutionStep, SkillReference
from ama_teammate.learned_metrics.models import ControlledMetricSpec
from ama_teammate.semantic_metadata.models import DefinitionReference
from ama_teammate.sql_policy.models import ValidatedQuery


class AnalysisKind(StrEnum):
    TREND = "trend"
    PERIOD_COMPARISON = "period_comparison"
    SEGMENT_BREAKDOWN = "segment_breakdown"
    CONTRIBUTION = "contribution"
    FUNNEL_RATE = "funnel_rate"
    QUALITY = "quality"
    ANOMALY = "anomaly"
    SEASONALITY = "seasonality"
    CORRELATION = "correlation"
    MIX_RATE_DECOMPOSITION = "mix_rate_decomposition"
    CROSS_SOURCE_RECONCILIATION = "cross_source_reconciliation"


class ChartKind(StrEnum):
    TABLE = "table"
    KPI = "kpi"
    LINE = "line"
    BAR = "bar"
    STACKED_BAR = "stacked_bar"
    STACKED_BAR_100 = "stacked_bar_100"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    HEATMAP = "heatmap"
    WATERFALL = "waterfall"
    FUNNEL = "funnel"


class AnalysisIntent(BaseModel):
    analysis_type: AnalysisKind
    metric: str
    dimensions: list[str] = Field(default_factory=list, max_length=5)
    source_ids: list[str] = Field(min_length=1, max_length=3)
    start_date: str = "2025-01-01"
    end_date: str = "2026-01-01"
    chart_type: ChartKind = ChartKind.TABLE
    success_criteria: str
    causal_design: bool = False
    metadata_confidence: Literal["authoritative", "working_assumption", "learned_definition"] = "authoritative"
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    calculation_spec: ControlledMetricSpec | None = None
    learned_metric_ref: str | None = None


class JoinPlan(BaseModel):
    left_source_id: str
    right_source_id: str
    left_key: str
    right_key: str
    join_type: str = "left"
    type_coercion: str = "string"
    max_output_rows: int = 1_000


class AnalysisPlan(BaseModel):
    id: str
    run_id: str
    question: str
    goal: str
    intent: AnalysisIntent
    queries: list[ValidatedQuery]
    join_plan: JoinPlan | None = None
    policy_version: str
    metric_definition: DefinitionReference
    relationship_definitions: list[DefinitionReference] = Field(default_factory=list)
    skill_execution_plan: list[SkillExecutionStep] = Field(default_factory=list)

    def approval_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.id,
            "run_id": self.run_id,
            "goal": self.goal,
            "analysis_type": self.intent.analysis_type.value,
            "metric": self.intent.metric,
            "chart_type": self.intent.chart_type.value,
            "metadata_confidence": self.intent.metadata_confidence,
            "assumptions": self.intent.assumptions,
            "queries": [query.approval_payload() for query in self.queries],
            "join_plan": self.join_plan.model_dump() if self.join_plan else None,
            "policy_version": self.policy_version,
            "metric_definition": self.metric_definition.model_dump(mode="json"),
            "relationship_definitions": [
                item.model_dump(mode="json") for item in self.relationship_definitions
            ],
            "skill_execution_plan": [
                item.model_dump(mode="json") for item in self.skill_execution_plan
            ],
        }


class DataConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNUSABLE = "unusable"


class DatasetQuality(BaseModel):
    row_count: int
    missing_by_column: dict[str, int]
    duplicate_rows: int
    duplicate_key_rows: int = 0
    warnings: list[str] = Field(default_factory=list)
    freshness: str = "unknown"
    completeness_rate: float = Field(default=1.0, ge=0, le=1)
    uniqueness_rate: float = Field(default=1.0, ge=0, le=1)
    volume_anomaly: bool = False
    schema_consistent: bool = True
    referential_integrity_rate: float | None = Field(default=None, ge=0, le=1)
    comparison_period_covered: bool = True
    confidence: DataConfidence = DataConfidence.HIGH


class Dataset(BaseModel):
    id: str
    source_ids: list[str]
    query_proposal_ids: list[str]
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    result_bytes: int
    quality: DatasetQuality


class NarrativeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class AnalysisNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1, max_length=1_500)
    confirmed_findings: list[NarrativeClaim] = Field(default_factory=list, max_length=8)
    inferred_findings: list[NarrativeClaim] = Field(default_factory=list, max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=8)
    next_actions: list[str] = Field(default_factory=list, max_length=6)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class JoinQuality(BaseModel):
    left_rows: int
    right_rows: int
    output_rows: int
    matched_left_rows: int
    left_unmatched_rate: float
    right_unmatched_rate: float
    duplicate_left_keys: int
    duplicate_right_keys: int
    type_coercion: str
    weak: bool
    warnings: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    id: str
    title: str
    dataset_ids: list[str]
    query_proposal_ids: list[str]
    calculation: str
    support: dict[str, Any]
    epistemic_label: str
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)


class Conclusion(BaseModel):
    text: str
    epistemic_label: str
    evidence_ids: list[str]


class AnalysisComputation(BaseModel):
    summary: dict[str, Any]
    conclusions: list[Conclusion]
    evidence: list[EvidenceRecord]


class ChartSpec(BaseModel):
    chart_type: ChartKind
    figure: dict[str, Any]
    dataset_id: str
    evidence_ids: list[str]
    fallback_table: bool = False


class AnalysisResult(BaseModel):
    id: str
    run_id: str
    plan_id: str
    status: str
    datasets: list[Dataset]
    join_quality: JoinQuality | None = None
    computation: AnalysisComputation
    chart: ChartSpec
    csv_artifact_id: str
    completed_at: str
    executive_summary: str = ""
    confirmed_findings: list[Conclusion] = Field(default_factory=list)
    inferred_findings: list[Conclusion] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    metric_references: list[DefinitionReference] = Field(default_factory=list)
    data_source_references: list[str] = Field(default_factory=list)
    executed_query_references: list[str] = Field(default_factory=list)
    skill_references: list[SkillReference] = Field(default_factory=list)
    data_confidence: DataConfidence = DataConfidence.HIGH
