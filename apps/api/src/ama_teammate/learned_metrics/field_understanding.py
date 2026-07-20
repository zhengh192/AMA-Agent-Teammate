from __future__ import annotations

from dataclasses import dataclass

from ama_teammate.data_access.models import DataSourceConfig
from ama_teammate.semantic_metadata.models import (
    DefinitionStatus,
    DefinitionType,
    FieldDefinition,
)
from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry


@dataclass(frozen=True, slots=True)
class FieldUnderstanding:
    source_id: str
    table: str
    physical_name: str
    data_type: str
    dataset_grain: str
    entity_field: str
    time_field: str
    semantic_type: str
    description: str
    allowed_values: tuple[str | int | float | bool, ...]
    confidence: str
    caveats: tuple[str, ...]


class FieldUnderstandingResolver:
    """Build a bounded, user-correctable hypothesis for every physical field."""

    _TABLE_DEFAULTS = {
        "visit_log": ("session", "session_id", "start_time"),
        "turn_log": ("turn", "turn_id", "start_time"),
        "telemetry_log": ("event", "event_id", "timestamp"),
    }

    def __init__(self, semantic_registry: SemanticMetadataRegistry | None = None) -> None:
        self.semantic_registry = semantic_registry

    def understand(self, source: DataSourceConfig, table: str, field: str) -> FieldUnderstanding:
        catalog = source.tables[table]
        column = next(item for item in catalog.columns if item.name == field)
        dataset_grain, entity_field, time_field = self._TABLE_DEFAULTS.get(
            table, ("row", field, field)
        )
        approved = self._approved(source.id, table, field)
        if approved is not None:
            return FieldUnderstanding(
                source_id=source.id,
                table=table,
                physical_name=field,
                data_type=column.data_type,
                dataset_grain=dataset_grain,
                entity_field=entity_field,
                time_field=time_field,
                semantic_type=approved.semantic_type.value,
                description=approved.description,
                allowed_values=tuple(approved.allowed_values),
                confidence="authoritative",
                caveats=tuple(approved.caveats),
            )
        semantic_type = self._infer_semantic_type(field, column.data_type)
        readable_name = field.replace("_", " ")
        description = column.description.strip() or (
            f"Physical {semantic_type} field '{field}'. Its business meaning is inferred from "
            f"the name and type and can be corrected by the user."
        )
        return FieldUnderstanding(
            source_id=source.id,
            table=table,
            physical_name=field,
            data_type=column.data_type,
            dataset_grain=dataset_grain,
            entity_field=entity_field,
            time_field=time_field,
            semantic_type=semantic_type,
            description=description,
            allowed_values=(),
            confidence="inferred",
            caveats=(f"The meaning of {readable_name} is a field-name hypothesis.",),
        )

    def normalize_allowed_value(
        self, understanding: FieldUnderstanding, value: str | int | float | bool
    ) -> str | int | float | bool:
        if not isinstance(value, str):
            return value
        normalized = self._normalized_value(value)
        matches = [
            item
            for item in understanding.allowed_values
            if self._normalized_value(str(item)) == normalized
        ]
        return matches[0] if len(matches) == 1 else value

    def _approved(self, source_id: str, table: str, field: str) -> FieldDefinition | None:
        if self.semantic_registry is None:
            return None
        definition_id = f"{source_id}.{table}.{field}"
        values = self.semantic_registry.list_definitions(
            DefinitionType.FIELD, DefinitionStatus.ACTIVE
        )
        matches = [
            item
            for item in values
            if isinstance(item, FieldDefinition) and item.id == definition_id
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _normalized_value(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    @staticmethod
    def _infer_semantic_type(field: str, data_type: str) -> str:
        name = field.casefold()
        physical_type = data_type.casefold()
        if name.endswith("_id") or name.endswith("_number"):
            return "identifier"
        if name.startswith("is_") or name.endswith("_flag") or "bool" in physical_type:
            return "boolean"
        if any(marker in name for marker in ("time", "date", "timestamp")):
            return "temporal"
        if any(marker in name for marker in ("score", "amount", "duration", "count", "rate")):
            return "quantitative"
        if any(marker in physical_type for marker in ("int", "decimal", "float", "double")):
            return "quantitative"
        if any(marker in physical_type for marker in ("text", "blob")):
            return "text"
        return "categorical"
