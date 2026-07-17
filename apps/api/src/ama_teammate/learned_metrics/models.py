from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MetricFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=120)
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in"] = "="
    value: str | int | float | bool | list[str | int | float | bool]


class ControlledMetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = "super_agent_uat"
    table: str = Field(min_length=1, max_length=120)
    aggregation: Literal["count", "count_distinct", "sum", "average", "min", "max", "ratio"]
    value_field: str = Field(min_length=1, max_length=120)
    time_field: str = Field(min_length=1, max_length=120)
    filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    numerator_filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    denominator_filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    dimensions: list[str] = Field(default_factory=list, max_length=5)
    caveats: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_ratio(self) -> ControlledMetricSpec:
        if self.aggregation == "ratio" and not self.numerator_filters:
            raise ValueError("ratio metrics require numerator_filters")
        return self


class LearnedMetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    owner_id: str
    metric_key: str
    display_name: str
    aliases: list[str] = Field(min_length=1, max_length=30)
    version: int = Field(ge=1)
    status: Literal["active", "superseded", "deleted"] = "active"
    definition: ControlledMetricSpec
    source: str
    created_at: str | None = None


class MetricLearningRequired(ValueError):
    def __init__(
        self,
        metric_name: str,
        question: str,
        prompt: str,
        *,
        source_id: str = "super_agent_uat",
        example: str = "",
    ) -> None:
        super().__init__(prompt)
        self.metric_name = metric_name
        self.question = question
        self.prompt = prompt
        self.source_id = source_id
        self.example = example


class MetricLearningInputError(ValueError):
    pass


class LearnedMetricAmbiguousError(ValueError):
    def __init__(self, candidates: list[LearnedMetricDefinition]) -> None:
        self.candidates = candidates
        names = ", ".join(item.display_name for item in candidates)
        super().__init__(f"Multiple learned metrics match: {names}")
