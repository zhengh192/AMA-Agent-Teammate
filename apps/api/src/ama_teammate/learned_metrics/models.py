from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MetricFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=120)
    operator: Literal[
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "in",
        "not_in",
        "is_null",
        "is_not_null",
        "like",
        "not_like",
        "between",
    ] = "="
    value: str | int | float | bool | list[str | int | float | bool] | None = None

    @model_validator(mode="after")
    def validate_value_shape(self) -> MetricFilter:
        if self.operator in {"is_null", "is_not_null"}:
            if self.value is not None:
                raise ValueError(f"{self.operator} does not accept a value")
            return self
        if self.value is None:
            raise ValueError(f"{self.operator} requires a value")
        if self.operator in {"in", "not_in"}:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"{self.operator} requires a non-empty list")
        elif self.operator == "between":
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError("between requires exactly two values")
        elif isinstance(self.value, list):
            raise ValueError(f"{self.operator} requires a scalar value")
        return self



class MetricFilterGroup(BaseModel):
    """An AND group; multiple groups on a spec are combined with OR."""

    model_config = ConfigDict(extra="forbid")

    filters: list[MetricFilter] = Field(min_length=1, max_length=12)

class ControlledMetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = "super_agent_uat"
    table: str = Field(min_length=1, max_length=120)
    aggregation: Literal["count", "count_distinct", "sum", "average", "min", "max", "ratio"]
    value_field: str = Field(min_length=1, max_length=120)
    time_field: str = Field(min_length=1, max_length=120)
    time_grain: Literal["none", "day", "week", "month"] = "none"
    filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    numerator_filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    denominator_filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    filter_groups: list[MetricFilterGroup] = Field(default_factory=list, max_length=8)
    numerator_filter_groups: list[MetricFilterGroup] = Field(default_factory=list, max_length=8)
    denominator_filter_groups: list[MetricFilterGroup] = Field(default_factory=list, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=5)
    caveats: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_ratio(self) -> ControlledMetricSpec:
        if (
            self.aggregation == "ratio"
            and not self.numerator_filters
            and not self.numerator_filter_groups
        ):
            raise ValueError("ratio metrics require numerator_filters")
        return self



class AdHocQueryRequest(BaseModel):
    """Untrusted model output describing a query without containing SQL."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["metric", "detail"]
    display_name: str = Field(min_length=1, max_length=160)
    calculation: ControlledMetricSpec | None = None
    detail_table: Literal["visit_log", "turn_log", "telemetry_log"] | None = None
    detail_fields: list[str] = Field(default_factory=list, max_length=30)
    detail_limit: int = Field(default=50, ge=1, le=200)
    detail_filters: list[MetricFilter] = Field(default_factory=list, max_length=12)
    detail_filter_groups: list[MetricFilterGroup] = Field(default_factory=list, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_mode(self) -> AdHocQueryRequest:
        if self.mode == "metric" and self.calculation is None:
            raise ValueError("metric mode requires calculation")
        if self.mode == "detail" and (self.detail_table is None or not self.detail_fields):
            raise ValueError("detail mode requires a table and explicit fields")
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
        missing_fields: list[str] | None = None,
    ) -> None:
        super().__init__(prompt)
        self.metric_name = metric_name
        self.question = question
        self.prompt = prompt
        self.source_id = source_id
        self.example = example
        self.missing_fields = missing_fields or ["metric_definition"]


class MetricLearningInputError(ValueError):
    pass


class LearnedMetricAmbiguousError(ValueError):
    def __init__(self, candidates: list[LearnedMetricDefinition]) -> None:
        self.candidates = candidates
        names = ", ".join(item.display_name for item in candidates)
        super().__init__(f"Multiple learned metrics match: {names}")
