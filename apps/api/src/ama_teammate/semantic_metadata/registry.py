from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml
from pydantic import BaseModel, ValidationError

from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.semantic_metadata.models import (
    BusinessRuleFile,
    DatasetDefinition,
    DataSourceDefinition,
    DataSourceFile,
    DefinitionStatus,
    DefinitionType,
    FieldDefinition,
    FieldFile,
    MetricDefinition,
    MetricFile,
    RelationshipDefinition,
    RelationshipFile,
    ResolvedAnalysisMetadata,
    SemanticDefinition,
)

T = TypeVar("T", bound=SemanticDefinition)


@dataclass(frozen=True, slots=True)
class MetadataValidationIssue:
    path: str
    code: str
    message: str
    definition_id: str | None = None
    version: str | None = None
    active: bool = False

    def safe_details(self) -> dict[str, str | bool | None]:
        return {
            "path": self.path,
            "code": self.code,
            "definition_id": self.definition_id,
            "version": self.version,
            "active": self.active,
        }


class SemanticMetadataValidationError(RuntimeError):
    def __init__(self, issues: list[MetadataValidationIssue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{item.path}: {item.code}" for item in issues[:5])
        super().__init__(f"Semantic metadata validation failed: {summary}")


class MetadataResolutionError(RuntimeError):
    pass


class MetadataMissingError(MetadataResolutionError):
    pass


class MetadataAmbiguousError(MetadataResolutionError):
    def __init__(self, term: str, matches: list[MetricDefinition]) -> None:
        self.term = term
        self.matches = matches
        ids = ", ".join(f"{item.id}@{item.version}" for item in matches)
        super().__init__(f"Metric term '{term}' is ambiguous: {ids}")


class MetadataSchemaConflictError(MetadataResolutionError):
    pass


def _normalized(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _is_active(raw: Any) -> bool:
    if isinstance(raw, dict):
        if raw.get("status") == "active":
            return True
        return any(_is_active(value) for value in raw.values())
    if isinstance(raw, list):
        return any(_is_active(value) for value in raw)
    return False


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors(include_input=False, include_url=False)[0]
    location = ".".join(str(item) for item in first.get("loc", ()))
    return f"{location}: {first.get('msg', 'invalid definition')}"


class SemanticMetadataRegistry:
    def __init__(self, definitions: list[SemanticDefinition]) -> None:
        self._definitions = definitions
        self._by_type: dict[DefinitionType, list[SemanticDefinition]] = defaultdict(list)
        self._by_key: dict[tuple[DefinitionType, str, str], SemanticDefinition] = {}
        for definition in definitions:
            definition_type = self.definition_type(definition)
            key = (definition_type, definition.id, definition.version)
            if key in self._by_key:
                raise ValueError(
                    f"Duplicate semantic definition: {definition_type.value}/{definition.id}@{definition.version}"
                )
            self._by_key[key] = definition
            self._by_type[definition_type].append(definition)

    @classmethod
    def load(cls, root: Path) -> tuple[SemanticMetadataRegistry, list[MetadataValidationIssue]]:
        definitions: list[SemanticDefinition] = []
        issues: list[MetadataValidationIssue] = []
        specifications: list[tuple[Path, type[BaseModel]]] = []
        specifications.extend((path, DataSourceFile) for path in sorted((root / "data_sources").glob("*.yaml")))
        specifications.extend((path, FieldFile) for path in sorted((root / "fields").glob("*.yaml")))
        specifications.extend((path, MetricFile) for path in sorted((root / "metrics").glob("*.yaml")))
        specifications.extend(
            [
                (root / "relationships.yaml", RelationshipFile),
                (root / "business_rules.yaml", BusinessRuleFile),
            ]
        )
        for path, model in specifications:
            relative = path.relative_to(root).as_posix()
            if not path.exists():
                issues.append(
                    MetadataValidationIssue(relative, "file_missing", "Required metadata file is missing.", active=True)
                )
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError, UnicodeError):
                issues.append(
                    MetadataValidationIssue(relative, "yaml_invalid", "YAML could not be read.", active=True)
                )
                continue
            try:
                parsed = model.model_validate(raw)
            except ValidationError as exc:
                issues.append(
                    MetadataValidationIssue(
                        relative,
                        "schema_invalid",
                        _validation_message(exc),
                        active=_is_active(raw),
                    )
                )
                continue
            definitions.extend(cls._file_definitions(parsed))

        try:
            registry = cls(definitions)
        except ValueError as exc:
            issues.append(
                MetadataValidationIssue("knowledge", "duplicate_definition", str(exc), active=True)
            )
            registry = cls(cls._deduplicate(definitions))
        cross_reference_issues = registry._validate_cross_references()
        if cross_reference_issues:
            rejected = {(item.definition_id, item.version) for item in cross_reference_issues}
            definitions = [
                item for item in registry._definitions if (item.id, item.version) not in rejected
            ]
            registry = cls(definitions)
            issues.extend(cross_reference_issues)
        return registry, issues

    @staticmethod
    def _file_definitions(parsed: BaseModel) -> list[SemanticDefinition]:
        if isinstance(parsed, DataSourceFile):
            return [parsed.definition, *parsed.definition.datasets]
        if isinstance(parsed, (FieldFile, MetricFile, RelationshipFile, BusinessRuleFile)):
            return list(parsed.definitions)
        raise TypeError("Unsupported semantic metadata file")

    @staticmethod
    def _deduplicate(definitions: list[SemanticDefinition]) -> list[SemanticDefinition]:
        result: list[SemanticDefinition] = []
        seen: set[tuple[DefinitionType, str, str]] = set()
        for item in definitions:
            key = (SemanticMetadataRegistry.definition_type(item), item.id, item.version)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def definition_type(definition: SemanticDefinition) -> DefinitionType:
        return DefinitionType(definition.kind)

    def list_definitions(
        self,
        definition_type: DefinitionType | None = None,
        status: DefinitionStatus | None = None,
    ) -> list[SemanticDefinition]:
        values = (
            list(self._by_type.get(definition_type, []))
            if definition_type is not None
            else list(self._definitions)
        )
        if status is not None:
            values = [item for item in values if item.status == status]
        return sorted(values, key=lambda item: (item.kind, item.id, item.version))

    def get(
        self, definition_type: DefinitionType, definition_id: str, version: str | None = None
    ) -> SemanticDefinition:
        matches = [
            item
            for item in self._by_type.get(definition_type, [])
            if item.id == definition_id and (version is None or item.version == version)
        ]
        if version is None:
            active = [item for item in matches if self._effective(item)]
            matches = active or matches
        if not matches:
            raise LookupError(f"Semantic definition not found: {definition_type.value}/{definition_id}")
        return sorted(matches, key=lambda item: item.version)[-1]

    def search(
        self,
        query: str,
        definition_type: DefinitionType | None = None,
        status: DefinitionStatus | None = None,
    ) -> list[SemanticDefinition]:
        term = _normalized(query)
        if not term:
            return []
        results: list[SemanticDefinition] = []
        for item in self.list_definitions(definition_type, status):
            text = [item.id, item.name, item.description]
            if isinstance(item, MetricDefinition):
                text.extend(item.aliases)
            if term in _normalized(" ".join(text)):
                results.append(item)
        return results

    def resolve_metric(
        self, term: str, *, context: str = "", allow_draft: bool = False
    ) -> MetricDefinition:
        normalized = _normalized(term)
        metrics = cast(list[MetricDefinition], self._by_type.get(DefinitionType.METRIC, []))
        matches = [
            item
            for item in metrics
            if (self._effective(item) or (allow_draft and item.status == DefinitionStatus.DRAFT))
            and normalized in {_normalized(item.id), _normalized(item.name), *map(_normalized, item.aliases)}
        ]
        if not matches:
            raise MetadataMissingError(
                f"Unknown: no active approved metric definition matches '{term}'."
            )
        if len(matches) > 1:
            context_normalized = _normalized(context)
            explicit = [
                item
                for item in matches
                if _normalized(item.id) in context_normalized
                or _normalized(item.name) in context_normalized
            ]
            if len(explicit) == 1:
                return explicit[0]
            raise MetadataAmbiguousError(term, matches)
        return matches[0]

    def resolve_analysis_metadata(
        self,
        metric_term: str,
        dimensions: list[str],
        *,
        context: str,
        connectors: ConnectorRegistry,
    ) -> ResolvedAnalysisMetadata:
        metric = self.resolve_metric(metric_term, context=context)
        active_fields = cast(list[FieldDefinition], self._by_type[DefinitionType.FIELD])
        referenced_ids = set(metric.supported_dimensions)
        if metric.numerator:
            referenced_ids.update(metric.numerator.field_references)
        if metric.denominator:
            referenced_ids.update(metric.denominator.field_references)
        referenced_ids.add(metric.time_logic.event_time_field)
        for dimension in dimensions:
            normalized = _normalized(dimension)
            referenced_ids.update(
                item.id
                for item in active_fields
                if self._effective(item)
                and normalized in {_normalized(item.id), _normalized(item.name), _normalized(item.physical_name)}
                and item.id in metric.supported_dimensions
            )
        fields = [
            item for item in active_fields if self._effective(item) and item.id in referenced_ids
        ]
        relationships = cast(
            list[RelationshipDefinition], self._by_type[DefinitionType.RELATIONSHIP]
        )
        dataset_ids = set(metric.source_datasets)
        selected_relationships = [
            item
            for item in relationships
            if self._effective(item)
            and item.left_dataset_id in dataset_ids
            and item.right_dataset_id in dataset_ids
        ]
        self._validate_connector_schema(metric, fields, connectors)
        return ResolvedAnalysisMetadata(
            metric=metric, fields=fields, relationships=selected_relationships
        )

    def _validate_connector_schema(
        self,
        metric: MetricDefinition,
        fields: list[FieldDefinition],
        connectors: ConnectorRegistry,
    ) -> None:
        datasets = {
            item.id: item
            for item in cast(list[DatasetDefinition], self._by_type[DefinitionType.DATASET])
            if self._effective(item)
        }
        sources = {
            item.id: item
            for item in cast(list[DataSourceDefinition], self._by_type[DefinitionType.DATA_SOURCE])
            if self._effective(item)
        }
        fields_by_dataset: dict[str, list[FieldDefinition]] = defaultdict(list)
        for field in fields:
            fields_by_dataset[field.dataset_id].append(field)
        for dataset_id in metric.source_datasets:
            dataset = datasets.get(dataset_id)
            if dataset is None:
                raise MetadataSchemaConflictError(
                    f"Metadata conflict: dataset '{dataset_id}' is not active."
                )
            source = sources.get(dataset.data_source_id)
            if source is None:
                raise MetadataSchemaConflictError(
                    f"Metadata conflict: data source '{dataset.data_source_id}' is not active."
                )
            try:
                config = connectors.config(source.connection_name)
            except KeyError as exc:
                raise MetadataSchemaConflictError(
                    f"Metadata conflict: connector '{source.connection_name}' is not configured."
                ) from exc
            table = config.tables.get(dataset.physical_name)
            if table is None:
                raise MetadataSchemaConflictError(
                    f"Metadata conflict: dataset '{dataset.physical_name}' is absent from connector '{source.connection_name}'."
                )
            columns = {column.name: column for column in table.columns}
            for field in fields_by_dataset[dataset_id]:
                column = columns.get(field.physical_name)
                if column is None:
                    raise MetadataSchemaConflictError(
                        f"Metadata conflict: field '{field.physical_name}' is absent from dataset '{dataset.physical_name}'."
                    )
                if column.nullable != field.nullable:
                    raise MetadataSchemaConflictError(
                        f"Metadata conflict: nullability differs for '{dataset.physical_name}.{field.physical_name}'."
                    )

    def _validate_cross_references(self) -> list[MetadataValidationIssue]:
        issues: list[MetadataValidationIssue] = []
        active_ids: dict[DefinitionType, set[str]] = {
            kind: {item.id for item in values if self._effective(item)}
            for kind, values in self._by_type.items()
        }
        field_dataset = {
            item.id: item.dataset_id
            for item in cast(list[FieldDefinition], self._by_type[DefinitionType.FIELD])
            if self._effective(item)
        }

        def issue(item: SemanticDefinition, code: str, message: str) -> None:
            issues.append(
                MetadataValidationIssue(
                    path=f"{item.kind}/{item.id}",
                    code=code,
                    message=message,
                    definition_id=item.id,
                    version=item.version,
                    active=item.status == DefinitionStatus.ACTIVE,
                )
            )

        for dataset in cast(list[DatasetDefinition], self._by_type[DefinitionType.DATASET]):
            if self._effective(dataset) and dataset.data_source_id not in active_ids.get(
                DefinitionType.DATA_SOURCE, set()
            ):
                issue(dataset, "data_source_reference_invalid", "Dataset references an inactive data source.")
        for field in cast(list[FieldDefinition], self._by_type[DefinitionType.FIELD]):
            if self._effective(field) and field.dataset_id not in active_ids.get(
                DefinitionType.DATASET, set()
            ):
                issue(field, "dataset_reference_invalid", "Field references an inactive dataset.")
        for metric in cast(list[MetricDefinition], self._by_type[DefinitionType.METRIC]):
            if not self._effective(metric):
                continue
            refs = [*metric.source_datasets]
            if any(item not in active_ids.get(DefinitionType.DATASET, set()) for item in refs):
                issue(metric, "metric_dataset_reference_invalid", "Metric references an inactive dataset.")
                continue
            field_refs = [*metric.supported_dimensions, metric.time_logic.event_time_field]
            if metric.numerator:
                field_refs.extend(metric.numerator.field_references)
            if metric.denominator:
                field_refs.extend(metric.denominator.field_references)
            if any(item not in field_dataset for item in field_refs):
                issue(metric, "metric_field_reference_invalid", "Metric references an inactive field.")
        for relationship in cast(
            list[RelationshipDefinition], self._by_type[DefinitionType.RELATIONSHIP]
        ):
            if not self._effective(relationship):
                continue
            if relationship.left_dataset_id not in active_ids.get(
                DefinitionType.DATASET, set()
            ) or relationship.right_dataset_id not in active_ids.get(DefinitionType.DATASET, set()):
                issue(relationship, "relationship_dataset_reference_invalid", "Relationship references an inactive dataset.")
                continue
            for key in relationship.join_keys:
                if field_dataset.get(key.left_field_id) != relationship.left_dataset_id or field_dataset.get(
                    key.right_field_id
                ) != relationship.right_dataset_id:
                    issue(relationship, "relationship_key_reference_invalid", "Join key does not belong to the declared dataset.")
                    break
        return issues

    @staticmethod
    def _effective(item: SemanticDefinition) -> bool:
        today = date.today()
        return (
            item.status == DefinitionStatus.ACTIVE
            and item.effective_from <= today
            and (item.effective_to is None or item.effective_to >= today)
        )
