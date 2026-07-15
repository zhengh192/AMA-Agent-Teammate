from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120, pattern=r"^[a-z][a-z0-9_.-]+$"),
]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DefinitionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class DefinitionType(StrEnum):
    DATA_SOURCE = "data_source"
    DATASET = "dataset"
    FIELD = "field"
    METRIC = "metric"
    RELATIONSHIP = "relationship"
    BUSINESS_RULE = "business_rule"


class LifecycleDefinition(StrictModel):
    id: Identifier
    version: Version
    status: DefinitionStatus
    name: NonEmpty
    description: NonEmpty
    owner: NonEmpty
    source: NonEmpty
    effective_from: date
    effective_to: date | None = None
    last_reviewed_at: date

    @model_validator(mode="after")
    def validate_dates(self) -> LifecycleDefinition:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class DatasetDefinition(LifecycleDefinition):
    kind: Literal["dataset"] = "dataset"
    data_source_id: Identifier
    physical_name: Identifier
    schema_name: Identifier | None = None
    grain: NonEmpty
    primary_key_fields: list[Identifier] = Field(default_factory=list, max_length=20)
    caveats: list[NonEmpty] = Field(default_factory=list, max_length=20)


class DataSourceDefinition(LifecycleDefinition):
    kind: Literal["data_source"] = "data_source"
    platform: Literal["postgresql", "mysql", "sql_server", "file"]
    connection_name: Identifier
    read_only: Literal[True]
    datasets: list[DatasetDefinition] = Field(min_length=1, max_length=100)


class FieldGrain(StrEnum):
    PRIMARY_KEY = "primary_key"
    EVENT_KEY = "event_key"
    DIMENSION = "dimension"
    MEASURE = "measure"
    TIMESTAMP = "timestamp"
    ATTRIBUTE = "attribute"


class SemanticType(StrEnum):
    IDENTIFIER = "identifier"
    CATEGORICAL = "categorical"
    QUANTITATIVE = "quantitative"
    TEMPORAL = "temporal"
    BOOLEAN = "boolean"
    TEXT = "text"


class JoinUsage(StrEnum):
    PROHIBITED = "prohibited"
    ALLOWED = "allowed"
    PREFERRED = "preferred"
    CONDITIONAL = "conditional"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


AllowedValue = str | int | float | bool


class FieldDefinition(LifecycleDefinition):
    kind: Literal["field"] = "field"
    dataset_id: Identifier
    physical_name: Identifier
    data_type: NonEmpty
    grain: FieldGrain
    semantic_type: SemanticType
    nullable: bool
    allowed_values: list[AllowedValue] = Field(default_factory=list, max_length=250)
    join_usage: JoinUsage
    sensitivity: Sensitivity
    caveats: list[NonEmpty] = Field(default_factory=list, max_length=20)


class MetricComponent(StrictModel):
    expression: NonEmpty
    description: NonEmpty
    aggregation: Literal["sum", "count", "count_distinct", "average", "ratio", "custom"]
    distinct_by: list[Identifier] = Field(default_factory=list, max_length=20)
    field_references: list[Identifier] = Field(default_factory=list, max_length=30)


class TimeLogic(StrictModel):
    event_time_field: Identifier
    timezone: NonEmpty
    window: NonEmpty
    late_arrival_policy: NonEmpty


class MetricDefinition(LifecycleDefinition):
    kind: Literal["metric"] = "metric"
    aliases: list[NonEmpty] = Field(default_factory=list, max_length=50)
    numerator: MetricComponent | None = None
    denominator: MetricComponent | None = None
    formula: NonEmpty
    distinct_logic: NonEmpty
    filters: list[NonEmpty] = Field(default_factory=list, max_length=50)
    exclusions: list[NonEmpty] = Field(default_factory=list, max_length=50)
    time_logic: TimeLogic
    supported_dimensions: list[Identifier] = Field(default_factory=list, max_length=50)
    source_datasets: list[Identifier] = Field(min_length=1, max_length=20)
    interpretation_cautions: list[NonEmpty] = Field(default_factory=list, max_length=30)
    business_rule_ids: list[Identifier] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_aliases(self) -> MetricDefinition:
        values = [self.name, *self.aliases]
        normalized = [value.casefold().strip() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("metric name and aliases must be unique")
        return self


class JoinKey(StrictModel):
    left_field_id: Identifier
    right_field_id: Identifier
    type_coercion: NonEmpty | None = None


class TimeWindowMatching(StrictModel):
    enabled: bool
    left_time_field_id: Identifier | None = None
    right_time_field_id: Identifier | None = None
    tolerance: NonEmpty | None = None
    direction: Literal["backward", "forward", "nearest", "exact"] | None = None

    @model_validator(mode="after")
    def validate_enabled_fields(self) -> TimeWindowMatching:
        if self.enabled and not all(
            (self.left_time_field_id, self.right_time_field_id, self.tolerance, self.direction)
        ):
            raise ValueError("enabled time-window matching requires fields, tolerance, and direction")
        return self


class RelationshipDefinition(LifecycleDefinition):
    kind: Literal["relationship"] = "relationship"
    left_dataset_id: Identifier
    right_dataset_id: Identifier
    join_keys: list[JoinKey] = Field(min_length=1, max_length=10)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    time_window_matching: TimeWindowMatching
    duplication_risks: list[NonEmpty] = Field(min_length=1, max_length=20)
    automatic_join_allowed: bool
    cross_database: bool
    caveats: list[NonEmpty] = Field(default_factory=list, max_length=20)
    business_rule_ids: list[Identifier] = Field(default_factory=list, max_length=30)


class BusinessRuleDefinition(LifecycleDefinition):
    kind: Literal["business_rule"] = "business_rule"
    statement: NonEmpty
    expression: NonEmpty | None = None
    applies_to: list[Identifier] = Field(min_length=1, max_length=50)
    references: list[Identifier] = Field(default_factory=list, max_length=50)
    severity: Literal["informational", "warning", "blocking"]
    caveats: list[NonEmpty] = Field(default_factory=list, max_length=20)


class DataSourceFile(StrictModel):
    schema_version: Literal[1]
    kind: Literal["data_source_file"]
    definition: DataSourceDefinition


class FieldFile(StrictModel):
    schema_version: Literal[1]
    kind: Literal["field_file"]
    definitions: list[FieldDefinition] = Field(min_length=1)


class MetricFile(StrictModel):
    schema_version: Literal[1]
    kind: Literal["metric_file"]
    definitions: list[MetricDefinition] = Field(min_length=1)


class RelationshipFile(StrictModel):
    schema_version: Literal[1]
    kind: Literal["relationship_file"]
    definitions: list[RelationshipDefinition] = Field(min_length=1)


class BusinessRuleFile(StrictModel):
    schema_version: Literal[1]
    kind: Literal["business_rule_file"]
    definitions: list[BusinessRuleDefinition] = Field(min_length=1)


SemanticDefinition = (
    DataSourceDefinition
    | DatasetDefinition
    | FieldDefinition
    | MetricDefinition
    | RelationshipDefinition
    | BusinessRuleDefinition
)


class DefinitionReference(StrictModel):
    definition_type: DefinitionType
    id: Identifier
    version: Version


class ResolvedAnalysisMetadata(StrictModel):
    metric: MetricDefinition
    fields: list[FieldDefinition]
    relationships: list[RelationshipDefinition]
