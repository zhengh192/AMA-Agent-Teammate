from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from sqlalchemy import select

from ama_teammate.data_access.models import DataSourceConfig
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.domain.models import new_id, utc_now
from ama_teammate.learned_metrics.field_understanding import FieldUnderstandingResolver
from ama_teammate.learned_metrics.models import (
    ControlledMetricSpec,
    LearnedMetricAmbiguousError,
    LearnedMetricDefinition,
    MetricFilter,
    MetricLearningInputError,
    MetricLearningRequired,
)
from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry
from ama_teammate.storage.database import Database
from ama_teammate.storage.learned_metric_schema import LearnedMetricRow
from ama_teammate.storage.repositories import Repository

_SOURCE_WORDS = (
    "super agent",
    "superagent",
    "uat",
    "sa",
    "目前",
    "当前",
    "整体",
    "现在",
    "please",
    "show",
    "calculate",
    "compute",
    "what is",
    "how many",
    "是多少",
    "有多少",
    "多少",
    "的",
    "change",
    "update",
    "redefine",
    "correct",
    "definition",
    "formula",
    "修改",
    "更新",
    "更正",
    "重新定义",
    "定义",
    "公式",
    "改成",
)
_TABLE_ALIASES = {
    "visit_log": ("visit_log", "visit", "session", "访问", "会话"),
    "turn_log": ("turn_log", "turn", "轮次", "对话轮"),
    "telemetry_log": ("telemetry_log", "telemetry", "event", "埋点", "事件"),
}
_DEFAULT_FIELDS = {
    "visit_log": ("session_id", "start_time"),
    "turn_log": ("turn_id", "start_time"),
    "telemetry_log": ("event_id", "timestamp"),
}
_LOGICAL_TRUE_VALUE_OVERRIDES: dict[str, str | bool] = {"is_cid": "1"}
_NARRATIVE_STOPWORDS = {
    "a",
    "all",
    "and",
    "are",
    "count",
    "customer",
    "customers",
    "field",
    "how",
    "is",
    "many",
    "number",
    "of",
    "percent",
    "percentage",
    "records",
    "session",
    "sessions",
    "the",
    "to",
    "type",
    "user",
    "users",
    "would",
}
_ACCEPTANCE_MARKERS = (
    "accept",
    "accepted",
    "agree",
    "agreed",
    "yes",
    "true",
    "\u540c\u610f",
    "\u63a5\u53d7",
    "\u4e3a\u771f",
)
_TRUTHY_STRING_VALUES: list[str | int | bool] = [
    "yes",
    "Yes",
    "true",
    "True",
    "1",
    "accept",
    "accepted",
]


def normalize_term(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def is_definition_change_request(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "change",
            "update",
            "redefine",
            "correct",
            "definition",
            "formula",
            "修改",
            "更新",
            "更正",
            "重新定义",
            "定义",
            "公式",
            "改成",
        )
    )


def extract_metric_name(question: str) -> str:
    value = question.strip()
    value = re.sub(r"(?<![A-Za-z0-9_])SA(?![A-Za-z0-9_])", " ", value, flags=re.I)
    for word in _SOURCE_WORDS:
        value = re.sub(re.escape(word), " ", value, flags=re.I)
    value = re.sub(r"\b(in|from|for|total|overall|current)\b", " ", value, flags=re.I)
    value = re.sub(r"[?？!！。,:：;；]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_")
    return value[:120] or question.strip()[:120] or "unnamed metric"


class LearnedMetricService:
    """Persist explicit user-taught metric calculations and resolve tolerant aliases."""

    def __init__(
        self,
        database: Database,
        registry: ConnectorRegistry,
        repository: Repository,
        semantic_registry: SemanticMetadataRegistry | None = None,
    ) -> None:
        self.database = database
        self.registry = registry
        self.repository = repository
        self.field_understanding = FieldUnderstandingResolver(semantic_registry)

    async def list_active(self, owner_id: str) -> list[LearnedMetricDefinition]:
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(
                    select(LearnedMetricRow)
                    .where(
                        LearnedMetricRow.owner_id == owner_id,
                        LearnedMetricRow.status == "active",
                    )
                    .order_by(LearnedMetricRow.display_name, LearnedMetricRow.version.desc())
                )
            ).all()
        return [self._view(row) for row in rows]

    async def get(self, owner_id: str, definition_id: str) -> LearnedMetricDefinition | None:
        async with self.database.sessions() as session:
            row = await session.get(LearnedMetricRow, definition_id)
            if row is None or row.owner_id != owner_id:
                return None
        return self._view(row)

    async def search(self, owner_id: str, query: str) -> list[LearnedMetricDefinition]:
        definitions = await self.list_active(owner_id)
        needle = normalize_term(query)
        if not needle:
            return definitions
        ranked: list[tuple[float, LearnedMetricDefinition]] = []
        for definition in definitions:
            score = max(
                self._similarity(needle, normalize_term(alias))
                for alias in [definition.display_name, *definition.aliases]
            )
            if score >= 0.45:
                ranked.append((score, definition))
        return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)]

    async def resolve(
        self, owner_id: str, question: str, *, context: str = ""
    ) -> LearnedMetricDefinition | None:
        definitions = await self.list_active(owner_id)
        if not definitions:
            return None
        current = normalize_term(extract_metric_name(question))
        aliases_by_definition: list[tuple[set[str], LearnedMetricDefinition]] = []
        for definition in definitions:
            aliases = {definition.display_name, definition.metric_key, *definition.aliases}
            normalized = {normalize_term(alias) for alias in aliases if normalize_term(alias)}
            aliases_by_definition.append((normalized, definition))

        current_matches = [
            (max(len(alias) for alias in aliases if alias in current), definition)
            for aliases, definition in aliases_by_definition
            if any(alias in current for alias in aliases)
        ]
        if current_matches:
            longest = max(length for length, _ in current_matches)
            matches = self._unique([item for length, item in current_matches if length == longest])
            if len(matches) > 1:
                raise LearnedMetricAmbiguousError(matches)
            return matches[0]

        ranked = [
            (max(self._similarity(current, alias) for alias in aliases), definition)
            for aliases, definition in aliases_by_definition
        ]
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        if ranked and ranked[0][0] >= 0.78:
            close = self._unique([item for score, item in ranked if ranked[0][0] - score < 0.06])
            if len(close) > 1:
                raise LearnedMetricAmbiguousError(close)
            return ranked[0][1]

        follow_up_terms = {
            "byday",
            "daily",
            "trend",
            "bychannel",
            "byintent",
            "\u6309\u5929",
            "\u6bcf\u65e5",
            "\u8d8b\u52bf",
            "\u6309\u6e20\u9053",
            "\u6309\u610f\u56fe",
        }
        if current not in follow_up_terms:
            return None
        combined = normalize_term(context)
        context_matches = [
            (max(len(alias) for alias in aliases if alias in combined), definition)
            for aliases, definition in aliases_by_definition
            if any(alias in combined for alias in aliases)
        ]
        if not context_matches:
            return None
        longest = max(length for length, _ in context_matches)
        matches = self._unique([item for length, item in context_matches if length == longest])
        if len(matches) > 1:
            raise LearnedMetricAmbiguousError(matches)
        return matches[0]

    def infer_field_query(
        self, owner_id: str, question: str, *, context: str = ""
    ) -> LearnedMetricDefinition | None:
        """Infer a bounded entity count or value distribution from a physical field."""
        lowered = question.casefold()
        if any(
            marker in lowered
            for marker in (
                "rate",
                "ratio",
                "share",
                "percent",
                "percentage",
                "\u7387",
                "\u6bd4\u4f8b",
                "\u5360\u6bd4",
            )
        ):
            return None
        distribution = any(
            marker in lowered
            for marker in (
                "distribution",
                "distinct values",
                "value counts",
                "\u53d6\u503c\u5206\u5e03",
                "\u503c\u5206\u5e03",
                "\u6709\u54ea\u4e9b\u503c",
            )
        )
        selected = self._select_field_candidate(question)
        if selected is None and distribution:
            selected = self._select_field_candidate(context)
        if selected is None:
            return None
        table, field = selected
        source = self.registry.config("super_agent_uat")
        understanding = self.field_understanding.understand(source, table, field)
        condition_value = self._field_condition_value(question, field)
        if condition_value is None and not distribution:
            return None
        filters: list[MetricFilter] = []
        dimensions: list[str] = []
        if distribution:
            dimensions = [field]
            display_name = f"{field} \u53d6\u503c\u5206\u5e03"
            mode = "distribution"
        else:
            assert condition_value is not None
            physical_value = self.field_understanding.normalize_allowed_value(
                understanding, condition_value
            )
            filters = [MetricFilter(field=field, operator="=", value=physical_value)]
            display_name = (
                f"{field}={physical_value} \u7684{understanding.dataset_grain} \u6570\u91cf"
            )
            mode = "filtered-count"
        spec = ControlledMetricSpec(
            table=table,
            aggregation="count_distinct",
            value_field=understanding.entity_field,
            time_field=understanding.time_field,
            filters=filters,
            dimensions=dimensions,
            caveats=[
                f"{table} is treated as {understanding.dataset_grain} grain; "
                f"the query counts distinct {understanding.entity_field}.",
                f"Field meaning confidence is {understanding.confidence}: "
                f"{understanding.description}",
                *understanding.caveats,
            ],
        )
        return LearnedMetricDefinition(
            id=f"field-query-{table}-{field}-{mode}",
            owner_id=owner_id,
            metric_key=normalize_term(display_name),
            display_name=display_name,
            aliases=[display_name, question.strip()[:120]],
            version=1,
            definition=spec,
            source=(
                "Approved field metadata and deterministic physical query"
                if understanding.confidence == "authoritative"
                else "Inferred physical field query"
            ),
            created_at=utc_now().isoformat(),
        )

    def learning_request(self, question: str) -> MetricLearningRequired:
        metric_name = extract_metric_name(question)
        source = self.registry.config("super_agent_uat")
        denied = {item.casefold() for item in source.denied_columns}
        candidates = self._candidate_fields(source, question, denied)
        is_rate = any(
            marker in question.casefold()
            for marker in (
                "rate",
                "ratio",
                "share",
                "percent",
                "percentage",
                "\u7387",
                "\u6bd4\u4f8b",
                "\u5360\u6bd4",
            )
        )
        if len(candidates) == 1:
            table, field = candidates[0]
            value_field, time_field = _DEFAULT_FIELDS[table]
            if is_rate:
                prompt = (
                    f"\u6211\u7406\u89e3\u4f60\u8981\u7b97 {table}.{field} \u7684\u5360\u6bd4\uff0c"
                    f"\u7edf\u8ba1\u7c92\u5ea6\u662f {value_field}\uff0c\u65f6\u95f4\u5b57\u6bb5\u662f {time_field}\u3002"
                    "\u8bf7\u53ea\u786e\u8ba4\u4e24\u70b9\uff1a\u4ec0\u4e48\u503c\u7b97\u547d\u4e2d\uff0c"
                    "\u4ee5\u53ca\u5206\u6bcd\u662f\u5426\u4e3a\u5168\u90e8\u4f1a\u8bdd\u3002"
                )
                return MetricLearningRequired(
                    metric_name,
                    question,
                    prompt,
                    example=(
                        f"metric_name={metric_name}; table={table}; aggregation=ratio; "
                        f"value_field={value_field}; time_field={time_field}; "
                        f"numerator={field}:true; denominator=all"
                    ),
                    missing_fields=["numerator_value", "denominator_scope"],
                )
        if len(candidates) == 1:
            table, field = candidates[0]
            understanding = self.field_understanding.understand(source, table, field)
            allowed = (
                "\uff1b\u5df2\u77e5\u53d6\u503c\u6709 "
                + ", ".join(map(str, understanding.allowed_values))
                if understanding.allowed_values
                else "\uff1b\u5f53\u524d\u8fd8\u6ca1\u6709\u6279\u51c6\u7684\u53d6\u503c\u5b57\u5178"
            )
            prompt = (
                f"\u6211\u5df2\u7ecf\u627e\u5230 {table}.{field}\u3002{table} \u662f "
                f"{understanding.dataset_grain} \u7c92\u5ea6\uff0c\u9ed8\u8ba4\u6309 "
                f"{understanding.entity_field} \u53bb\u91cd\u8ba1\u6570\u3002"
                f"\u6211\u5bf9\u8fd9\u4e2a\u5b57\u6bb5\u7684\u7406\u89e3\u662f\uff1a"
                f"{understanding.description}{allowed}\u3002"
                "\u4f60\u53ef\u4ee5\u76f4\u63a5\u8bf4\u770b\u53d6\u503c\u5206\u5e03\u3001"
                "\u67d0\u4e2a\u503c\u7684 session \u6570\u6216\u6bd4\u4f8b\u3002"
            )
            return MetricLearningRequired(
                metric_name,
                question,
                prompt,
                example=f"\u4f8b\u5982\uff1a\u770b {field} \u7684\u53d6\u503c\u5206\u5e03\uff1b\u6216\u53ea\u770b {field}=yes \u7684 session\u3002",
                missing_fields=["field_intent"],
            )
        if is_rate:
            likely_fields = sorted(
                (
                    (score, table_name, field)
                    for table_name in source.tables
                    for score, field in self._field_scores(source, table_name, question)
                    if field.casefold() not in denied and score >= 0.82
                ),
                key=lambda item: (-item[0], item[1], item[2]),
            )[:5]
            hint = (
                " \u53ef\u80fd\u76f8\u5173\u7684\u5b57\u6bb5\uff1a"
                + ", ".join(f"{table_name}.{field}" for _, table_name, field in likely_fields)
                + "\u3002"
                if likely_fields
                else ""
            )
            prompt = (
                f"\u6211\u7406\u89e3\u201c{metric_name}\u201d\u662f\u4e00\u4e2a\u6bd4\u4f8b\u95ee\u9898\uff0c"
                "\u4f46\u8fd8\u6ca1\u6709\u552f\u4e00\u53e3\u5f84\u3002\u8bf7\u544a\u8bc9\u6211\u5206\u6bcd\u662f\u54ea\u4e9b sessions\uff0c"
                "\u4ee5\u53ca\u5206\u5b50\u5728\u8fd9\u4e9b sessions \u4e0a\u8fd8\u8981\u6ee1\u8db3\u4ec0\u4e48\u6761\u4ef6\u3002"
                "\u4e0d\u9700\u8981\u5199 field=value\uff0c\u7528\u81ea\u7136\u8bed\u8a00\u5373\u53ef\u3002"
                f"{hint}"
            )
            return MetricLearningRequired(
                metric_name,
                question,
                prompt,
                example=(
                    "\u4f8b\u5982\uff1a\u5206\u6bcd\u662f deliver type \u4e3a onsite \u7684\u5168\u90e8 sessions\uff0c"
                    "\u5206\u5b50\u662f\u8fd9\u4e9b sessions \u4e2d accept downgrade \u4e3a\u540c\u610f\u7684\u6570\u91cf\u3002"
                ),
                missing_fields=["denominator_population", "numerator_condition"],
            )
        table_summary = "; ".join(
            f"{table}: {', '.join(self._preview_fields(table, catalog, denied))}"
            for table, catalog in source.tables.items()
        )
        prompt = (
            f"\u6211\u5927\u6982\u7406\u89e3\u201c{metric_name}\u201d\uff0c\u4f46\u8fd8\u4e0d\u60f3\u66ff\u4f60\u731c\u53e3\u5f84\u3002"
            "\u8bf7\u8bf4\u5b83\u60f3\u6570\u4ec0\u4e48\uff0c\u77e5\u9053\u5b57\u6bb5\u540d\u5c31\u5e26\u4e0a\uff0c"
            "\u4e0d\u77e5\u9053\u4e5f\u6ca1\u5173\u7cfb\u3002"
            f"\u5f53\u524d\u53ef\u89c1\u5b57\u6bb5\uff1a{table_summary}\u3002"
        )
        return MetricLearningRequired(
            metric_name,
            question,
            prompt,
            example="\u8bf4\u660e\u8868\u3001\u4e1a\u52a1\u6761\u4ef6\u548c\u7edf\u8ba1\u5bf9\u8c61\u5373\u53ef\u3002",
            missing_fields=["table", "aggregation", "value_field", "time_field"],
        )

    def _select_field_candidate(self, text: str) -> tuple[str, str] | None:
        try:
            source = self.registry.config("super_agent_uat")
        except KeyError:
            return None
        denied = {item.casefold() for item in source.denied_columns}
        lowered = text.casefold()
        ranked: list[tuple[int, str, str]] = []
        for table, catalog in source.tables.items():
            for column in catalog.columns:
                if column.name.casefold() in denied:
                    continue
                position = max(
                    lowered.rfind(column.name.casefold()),
                    lowered.rfind(column.name.replace("_", " ").casefold()),
                )
                if position >= 0:
                    ranked.append((position, table, column.name))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        top_position = ranked[0][0]
        top = [(table, field) for position, table, field in ranked if position == top_position]
        return top[0] if len(top) == 1 else None

    @staticmethod
    def _field_condition_value(text: str, field: str) -> str | None:
        aliases = (re.escape(field), re.escape(field.replace("_", " ")))
        pattern = re.compile(
            rf"(?:{'|'.join(aliases)})\s*(?:=|:|\u53d6\u503c\u4e3a|\u503c\u4e3a|\u4e3a|\u662f)\s*"
            r"['\"]?([A-Za-z0-9_-]+)",
            re.I,
        )
        matched = pattern.search(text)
        return matched.group(1) if matched else None

    @staticmethod
    def _candidate_fields(
        source: DataSourceConfig, question: str, denied: set[str]
    ) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        for table_name, catalog in source.tables.items():
            for column in catalog.columns:
                if column.name.casefold() in denied:
                    continue
                if re.search(
                    rf"(?<![A-Za-z0-9_]){re.escape(column.name)}(?![A-Za-z0-9_])",
                    question,
                    re.I,
                ):
                    candidates.append((table_name, column.name))
        return candidates

    async def learn_from_clarification(
        self,
        *,
        owner_id: str,
        metric_name: str,
        original_question: str,
        clarification: str,
        session_id: str,
        run_id: str,
    ) -> LearnedMetricDefinition:
        source = self.registry.config("super_agent_uat")
        spec, display_name, aliases = self._parse_definition(
            source, metric_name, original_question, clarification
        )
        metric_key = self._metric_key(display_name)
        now = utc_now()
        async with self.database.sessions() as session:
            existing = (
                await session.scalars(
                    select(LearnedMetricRow).where(
                        LearnedMetricRow.owner_id == owner_id,
                        LearnedMetricRow.metric_key == metric_key,
                    )
                )
            ).all()
            version = max((row.version for row in existing), default=0) + 1
            for previous in existing:
                if previous.status == "active":
                    previous.status = "superseded"
                    previous.updated_at = now
            row = LearnedMetricRow(
                id=new_id(),
                owner_id=owner_id,
                metric_key=metric_key,
                display_name=display_name,
                aliases_json=json.dumps(aliases, ensure_ascii=False),
                version=version,
                status="active",
                definition_json=spec.model_dump_json(),
                source="Explicit user clarification in analysis chat",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
        await self.repository.add_audit_event(
            actor_id=owner_id,
            event_type="learned_metric.activated",
            status="success",
            session_id=session_id,
            run_id=run_id,
            graph_node="create_analysis_plan",
            input_text=clarification,
            safe_details={
                "definition_id": row.id,
                "metric_key": metric_key,
                "version": version,
                "table": spec.table,
                "aggregation": spec.aggregation,
                "value_field": spec.value_field,
                "time_field": spec.time_field,
                "alias_count": len(aliases),
            },
        )
        return self._view(row)

    @staticmethod
    def _preview_fields(table: str, catalog: object, denied: set[str]) -> list[str]:
        from ama_teammate.data_access.models import TableCatalog

        if not isinstance(catalog, TableCatalog):
            return []
        available = [
            column.name for column in catalog.columns if column.name.casefold() not in denied
        ]
        preferred = {
            "visit_log": (
                "session_id",
                "start_time",
                "to_agent_flag",
                "agent_working_hour",
                "is_foc",
                "touchless_exception",
                "survey_score",
                "survey_resolved",
                "channel",
                "intent_type",
            ),
            "turn_log": ("turn_id", "session_id", "start_time", "channel", "intent_type"),
            "telemetry_log": ("event_id", "session_id", "timestamp", "event_name"),
        }.get(table, ())
        ordered = [field for field in preferred if field in available]
        ordered.extend(field for field in sorted(available) if field not in ordered)
        return ordered[:12]

    def _parse_definition(
        self,
        source: DataSourceConfig,
        metric_name: str,
        original_question: str,
        clarification: str,
    ) -> tuple[ControlledMetricSpec, str, list[str]]:
        text = clarification.strip()
        if not text:
            raise MetricLearningInputError("The metric clarification was empty.")
        context_text = f"{original_question}\n{text}"
        named = self._named_parts(text)
        display_name = (
            named.get("metric_name")
            or named.get("\u6307\u6807\u540d")
            or named.get("name")
            or metric_name
        ).strip()
        table = self._resolve_table(source, named.get("table") or named.get("\u8868"), context_text)
        value_field = self._resolve_field(
            source,
            table,
            named.get("value_field")
            or named.get("\u7edf\u8ba1\u5b57\u6bb5")
            or named.get("\u5b57\u6bb5"),
            context_text,
            default=_DEFAULT_FIELDS.get(table, (None, None))[0],
        )
        time_field = self._resolve_field(
            source,
            table,
            named.get("time_field")
            or named.get("\u65f6\u95f4\u5b57\u6bb5")
            or named.get("\u65f6\u95f4"),
            context_text,
            default=_DEFAULT_FIELDS.get(table, (None, None))[1],
        )
        aggregation = self._aggregation(
            named.get("aggregation") or named.get("\u7edf\u8ba1\u65b9\u5f0f"),
            f"{metric_name} {context_text}",
        )
        filter_text = (
            named.get("filters")
            or named.get("filter")
            or named.get("\u8fc7\u6ee4")
            or self._natural_part(
                text, ("\u8fc7\u6ee4\u6761\u4ef6", "\u8fc7\u6ee4", "filter", "filters")
            )
            or ""
        )
        numerator_text = (
            named.get("numerator")
            or named.get("\u5206\u5b50\u6761\u4ef6")
            or named.get("\u5206\u5b50")
            or self._natural_part(text, ("\u5206\u5b50\u6761\u4ef6", "\u5206\u5b50", "numerator"))
            or ""
        )
        denominator_text = (
            named.get("denominator")
            or named.get("\u5206\u6bcd\u6761\u4ef6")
            or named.get("\u5206\u6bcd")
            or self._natural_part(text, ("\u5206\u6bcd\u6761\u4ef6", "\u5206\u6bcd", "denominator"))
            or ""
        )
        filters = self._parse_filter_flex(
            source, table, filter_text, context_text=context_text, role="filter"
        )
        numerator = self._parse_filter_flex(
            source, table, numerator_text, context_text=context_text, role="numerator"
        )
        denominator = self._parse_filter_flex(
            source, table, denominator_text, context_text=context_text, role="denominator"
        )
        if aggregation == "ratio" and not numerator:
            inferred = self._natural_ratio_condition(source, table, context_text)
            if inferred is not None:
                numerator = [inferred]
        if aggregation == "ratio" and not numerator:
            raise MetricLearningInputError(
                "\u8fd8\u7f3a\u5c11\u5206\u5b50\u6761\u4ef6\uff1a\u8bf7\u544a\u8bc9\u6211\u54ea\u4e2a\u5b57\u6bb5\u7684\u4ec0\u4e48\u503c\u7b97\u547d\u4e2d\u3002"
            )
        dimensions_value = (
            named.get("dimensions")
            or named.get("\u7ef4\u5ea6")
            or self._natural_part(text, ("\u7ef4\u5ea6", "dimensions", "dimension"))
            or ""
        )
        dimensions = [
            self._resolve_field(source, table, item, item)
            for item in re.split(r"[|/\u3001\s]+", dimensions_value)
            if item.strip()
        ]
        alias_text = (
            named.get("aliases")
            or named.get("\u522b\u540d")
            or self._natural_part(text, ("\u522b\u540d", "aliases", "alias"))
            or ""
        )
        aliases = [
            display_name,
            metric_name,
            extract_metric_name(original_question),
            *[item.strip() for item in re.split(r"[|/\u3001,\uFF0C]+", alias_text) if item.strip()],
        ]
        aliases = list(dict.fromkeys(item for item in aliases if item))[:30]
        spec = ControlledMetricSpec(
            table=table,
            aggregation=aggregation,
            value_field=value_field,
            time_field=time_field,
            filters=filters,
            numerator_filters=numerator,
            denominator_filters=denominator,
            dimensions=dimensions,
            caveats=[
                "Definition was explicitly taught in chat and remains reviewable through SQL approval.",
                "Timezone remains unknown unless separately documented.",
                *(
                    [
                        "A narrative agreement field was interpreted with explicit truthy values; review the exact SQL parameters before approval."
                    ]
                    if any(item.operator == "in" for item in numerator)
                    else []
                ),
            ],
        )
        self.validate_spec(source, spec)
        return spec, display_name, aliases

    @staticmethod
    def validate_spec(source: DataSourceConfig, spec: ControlledMetricSpec) -> None:
        table = source.tables.get(spec.table)
        if table is None:
            raise MetricLearningInputError(f"Unknown or unauthorized table: {spec.table}")
        fields = {
            spec.value_field,
            spec.time_field,
            *spec.dimensions,
            *(item.field for item in spec.filters),
            *(item.field for item in spec.numerator_filters),
            *(item.field for item in spec.denominator_filters),
            *(
                item.field
                for group in spec.filter_groups
                for item in group.filters
            ),
            *(
                item.field
                for group in spec.numerator_filter_groups
                for item in group.filters
            ),
            *(
                item.field
                for group in spec.denominator_filter_groups
                for item in group.filters
            ),
        }
        denied = {item.casefold() for item in source.denied_columns}
        unknown = {item for item in fields if item.casefold() not in table.column_names}
        if unknown:
            raise MetricLearningInputError(
                f"Fields are not present in {spec.table}: {', '.join(sorted(unknown))}"
            )
        blocked = {item for item in fields if item.casefold() in denied}
        if blocked:
            raise MetricLearningInputError(
                f"Fields are not queryable: {', '.join(sorted(blocked))}"
            )

    def _resolve_table(self, source: DataSourceConfig, explicit: str | None, text: str) -> str:
        haystack = f"{explicit or ''} {text}".casefold()
        exact = [table for table in source.tables if table.casefold() in haystack]
        if len(exact) == 1:
            return exact[0]
        aliases = list(
            dict.fromkeys(
                table
                for table, terms in _TABLE_ALIASES.items()
                if table in source.tables and any(term in haystack for term in terms)
            )
        )
        if len(aliases) == 1:
            return aliases[0]
        mentioned = {
            column.name.casefold()
            for catalog in source.tables.values()
            for column in catalog.columns
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(column.name)}(?![A-Za-z0-9_])", text, re.I)
        }
        candidates = [
            table
            for table, catalog in source.tables.items()
            if mentioned and mentioned.issubset(catalog.column_names)
        ]
        if len(candidates) == 1:
            return candidates[0]
        raise MetricLearningInputError(
            "Please name exactly one table: " + ", ".join(sorted(source.tables))
        )

    def _resolve_field(
        self,
        source: DataSourceConfig,
        table: str,
        explicit: str | None,
        text: str,
        *,
        default: str | None = None,
    ) -> str:
        catalog = source.tables[table]
        candidates = [item.name for item in catalog.columns]
        haystack = explicit or text
        exact = [
            field
            for field in candidates
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", haystack, re.I)
        ]
        if explicit and len(exact) == 1:
            return exact[0]
        if explicit:
            needle = normalize_term(explicit)
            ranked = sorted(
                ((self._similarity(needle, normalize_term(field)), field) for field in candidates),
                reverse=True,
            )
            if (
                ranked
                and ranked[0][0] >= 0.86
                and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08)
            ):
                return ranked[0][1]
            raise MetricLearningInputError(
                f"I cannot uniquely map field ‘{explicit}’ in {table}. Use a physical field name."
            )
        if default and default.casefold() in catalog.column_names:
            return default
        if len(exact) == 1:
            return exact[0]
        raise MetricLearningInputError(f"Please name the calculation field in {table}.")

    def _parse_filter_flex(
        self,
        source: DataSourceConfig,
        table: str,
        value: str,
        *,
        context_text: str,
        role: str,
    ) -> list[MetricFilter]:
        try:
            return self._parse_filters(source, table, value)
        except MetricLearningInputError as strict_error:
            narrative = self._parse_narrative_filters(
                source, table, value, context_text=context_text, role=role
            )
            if narrative is not None:
                return narrative
            raise MetricLearningInputError(
                "\u6211\u7406\u89e3\u8fd9\u662f\u4e00\u4e2a\u4e1a\u52a1\u6761\u4ef6\uff0c"
                "\u4f46\u8fd8\u4e0d\u80fd\u552f\u4e00\u5bf9\u5e94\u5230\u7269\u7406\u5b57\u6bb5\u548c\u53d6\u503c\u3002"
            ) from strict_error

    def _parse_narrative_filters(
        self,
        source: DataSourceConfig,
        table: str,
        value: str,
        *,
        context_text: str,
        role: str,
    ) -> list[MetricFilter] | None:
        segment = value.strip()
        if not segment:
            return []
        lowered = segment.casefold()
        field = self._resolve_narrative_field(source, table, lowered)
        if any(marker in lowered for marker in _ACCEPTANCE_MARKERS):
            field = field or self._resolve_narrative_field(source, table, context_text)
            if field is None:
                return None
            understanding = self.field_understanding.understand(source, table, field)
            approved_truthy = [
                item
                for item in understanding.allowed_values
                if normalize_term(str(item)) in {"yes", "true", "1", "accept", "accepted"}
            ]
            if len(approved_truthy) == 1:
                return [MetricFilter(field=field, operator="=", value=approved_truthy[0])]
            if approved_truthy:
                return [MetricFilter(field=field, operator="in", value=approved_truthy)]
            if field.casefold() in _LOGICAL_TRUE_VALUE_OVERRIDES:
                return [
                    MetricFilter(
                        field=field,
                        operator="=",
                        value=_LOGICAL_TRUE_VALUE_OVERRIDES[field.casefold()],
                    )
                ]
            column = next(item for item in source.tables[table].columns if item.name == field)
            if any(marker in column.data_type.casefold() for marker in ("bool", "tinyint", "bit")):
                return [MetricFilter(field=field, operator="=", value=True)]
            return [MetricFilter(field=field, operator="in", value=list(_TRUTHY_STRING_VALUES))]

        literals = self._narrative_literals(segment, field)
        if not literals:
            return None
        literal = literals[0]
        if field is None:
            field = self._field_near_literal(source, table, context_text, literal)
        if field is None:
            return None
        understanding = self.field_understanding.understand(source, table, field)
        physical_literal = self.field_understanding.normalize_allowed_value(understanding, literal)
        return [MetricFilter(field=field, operator="=", value=physical_literal)]

    def _resolve_narrative_field(
        self, source: DataSourceConfig, table: str, text: str
    ) -> str | None:
        scores = self._field_scores(source, table, text)
        if not scores or scores[0][0] < 0.82:
            return None
        if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.18:
            return None
        return scores[0][1]

    def _field_near_literal(
        self,
        source: DataSourceConfig,
        table: str,
        context_text: str,
        literal: str,
    ) -> str | None:
        lowered = context_text.casefold()
        literal_position = lowered.find(literal.casefold())
        if literal_position < 0:
            return None
        ranked: list[tuple[float, int, str]] = []
        for score, field in self._field_scores(source, table, lowered):
            aliases = (field.casefold(), field.replace("_", " ").casefold())
            positions = [lowered.find(alias) for alias in aliases if lowered.find(alias) >= 0]
            if positions:
                distance = min(abs(position - literal_position) for position in positions)
                ranked.append((score, distance, field))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        return ranked[0][2]

    def _field_scores(
        self, source: DataSourceConfig, table: str, text: str
    ) -> list[tuple[float, str]]:
        lowered = text.casefold()
        normalized = normalize_term(lowered)
        query_tokens = re.findall(r"[a-z][a-z0-9]*", lowered)
        scored: list[tuple[float, str]] = []
        for column in source.tables[table].columns:
            field = column.name.casefold()
            spaced = field.replace("_", " ")
            score = 0.0
            if normalize_term(field) in normalized or normalize_term(spaced) in normalized:
                score = 5.0
            else:
                field_tokens = [
                    token
                    for token in field.split("_")
                    if token not in _NARRATIVE_STOPWORDS and len(token) > 2
                ]
                for field_token in field_tokens:
                    similarity = max(
                        (
                            SequenceMatcher(None, field_token, query_token).ratio()
                            for query_token in query_tokens
                        ),
                        default=0.0,
                    )
                    if similarity >= 0.82:
                        score += similarity
            if score > 0:
                scored.append((score, column.name))
        return sorted(scored, key=lambda item: (-item[0], item[1]))

    @staticmethod
    def _narrative_literals(value: str, field: str | None) -> list[str]:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", value)
        if quoted:
            return quoted
        field_tokens = set(field.casefold().split("_")) if field else set()
        result: list[str] = []
        for token in re.findall(r"[a-z][a-z0-9_-]*", value.casefold()):
            if token in _NARRATIVE_STOPWORDS or token in field_tokens:
                continue
            if any(marker in token for marker in ("accept", "agree", "downgrad")):
                continue
            if token not in result:
                result.append(token)
        return result

    def _parse_filters(
        self, source: DataSourceConfig, table: str, value: str
    ) -> list[MetricFilter]:
        if not value.strip() or value.strip().casefold() in {
            "all",
            "all rows",
            "all sessions",
            "\u5168\u90e8",
            "\u5168\u90e8\u4f1a\u8bdd",
            "\u5168\u90e8\u8bb0\u5f55",
            "\u65e0",
        }:
            return []
        result: list[MetricFilter] = []
        pattern = re.compile(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|!=|=|>|<|:|\uFF1A)\s*([^|\u3001]+?)"
            r"(?=(?:\s+(?:and|\u4e14)\s+|[|\u3001]|$))",
            re.I,
        )
        for field_value, operator, raw in pattern.findall(value.strip()):
            field = self._resolve_field(source, table, field_value, field_value)
            cleaned = raw.strip().strip("'\"")
            parsed: str | int | float | bool
            if cleaned.casefold() == "true":
                parsed = True
            elif cleaned.casefold() == "false":
                parsed = False
            else:
                try:
                    parsed = int(cleaned)
                except ValueError:
                    try:
                        parsed = float(cleaned)
                    except ValueError:
                        parsed = cleaned
            understanding = self.field_understanding.understand(source, table, field)
            physical_value = self.field_understanding.normalize_allowed_value(understanding, parsed)
            result.append(
                MetricFilter(
                    field=field,
                    operator="=" if operator in {":", "\uff1a"} else operator,
                    value=physical_value,
                )
            )
        if not result:
            raise MetricLearningInputError(
                "\u6211\u770b\u51fa\u4f60\u5728\u63cf\u8ff0\u7b5b\u9009\u6761\u4ef6\uff0c"
                "\u4f46\u8fd8\u4e0d\u80fd\u552f\u4e00\u6620\u5c04\u5230\u5b57\u6bb5\u548c\u53d6\u503c\u3002"
            )
        return result

    def _natural_ratio_condition(
        self, source: DataSourceConfig, table: str, text: str
    ) -> MetricFilter | None:
        matches = [
            column.name
            for column in source.tables[table].columns
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(column.name)}(?![A-Za-z0-9_])",
                text,
                re.I,
            )
        ]
        logical_markers = (
            "true",
            "yes",
            "\u4e3a\u771f",
            "\u662f",
            "\u7b49\u4e8e1",
            "\u53d6\u503c\u4e3a1",
        )
        if len(set(matches)) != 1 or not any(
            marker in text.casefold() for marker in logical_markers
        ):
            return None
        field = matches[0]
        understanding = self.field_understanding.understand(source, table, field)
        approved_truthy = [
            item
            for item in understanding.allowed_values
            if normalize_term(str(item)) in {"yes", "true", "1"}
        ]
        if approved_truthy:
            return MetricFilter(field=field, operator="=", value=approved_truthy[0])
        value: str | bool = _LOGICAL_TRUE_VALUE_OVERRIDES.get(field.casefold(), True)
        return MetricFilter(field=field, operator="=", value=value)

    @staticmethod
    def _aggregation(explicit: str | None, text: str) -> str:
        value = f"{explicit or ''} {text}".casefold()
        if any(
            item in value
            for item in ("ratio", "rate", "share", "percent", "percentage", "率", "比例", "占比")
        ):
            return "ratio"
        if any(item in value for item in ("count_distinct", "distinct", "去重")):
            return "count_distinct"
        if any(item in value for item in ("average", "avg", "平均", "均值")):
            return "average"
        if any(item in value for item in ("sum", "求和", "总和")):
            return "sum"
        if any(item in value for item in ("minimum", " min", "最小")):
            return "min"
        if any(item in value for item in ("maximum", " max", "最大")):
            return "max"
        if any(item in value for item in ("count", "数量", "个数", "多少")):
            return "count"
        raise MetricLearningInputError(
            "\u8bf7\u76f4\u63a5\u8bf4\u4f60\u60f3\u770b\u7684\u4e1a\u52a1\u7ed3\u679c\uff0c\u4f8b\u5982 session \u6570\u3001\u53d6\u503c\u5206\u5e03\u6216\u6bd4\u4f8b\u3002"
        )

    @staticmethod
    def _named_parts(text: str) -> dict[str, str]:
        aliases = {
            "metric_name",
            "指标名",
            "name",
            "table",
            "表",
            "value_field",
            "统计字段",
            "字段",
            "time_field",
            "时间字段",
            "时间",
            "aggregation",
            "统计方式",
            "filters",
            "filter",
            "过滤",
            "numerator",
            "分子条件",
            "分子",
            "denominator",
            "分母条件",
            "分母",
            "dimensions",
            "维度",
            "aliases",
            "别名",
        }
        key_pattern = "|".join(sorted((re.escape(item) for item in aliases), key=len, reverse=True))
        pattern = re.compile(
            rf"(?:^|[;；\n,，])\s*({key_pattern})\s*[:=：]\s*(.*?)"
            rf"(?=(?:[;；\n,，]\s*(?:{key_pattern})\s*[:=：])|$)",
            re.I,
        )
        return {key.casefold(): value.strip() for key, value in pattern.findall(text)}

    @staticmethod
    def _natural_part(text: str, markers: tuple[str, ...]) -> str | None:
        marker_pattern = "|".join(re.escape(item) for item in markers)
        stop_markers = (
            "指标名",
            "metric_name",
            "name",
            "表",
            "table",
            "统计方式",
            "aggregation",
            "统计字段",
            "value_field",
            "字段",
            "时间字段",
            "time_field",
            "时间",
            "过滤条件",
            "过滤",
            "filters",
            "filter",
            "分子条件",
            "分子",
            "numerator",
            "分母条件",
            "分母",
            "denominator",
            "维度",
            "dimensions",
            "dimension",
            "别名",
            "aliases",
            "alias",
        )
        stop_pattern = "|".join(re.escape(item) for item in stop_markers)
        match = re.search(
            rf"(?:{marker_pattern})\s*(?:is|are|是|为|用|叫|[:=：])?\s*(.*?)"
            rf"(?=(?:[;；,，]\s*(?:{stop_pattern}))|$)",
            text,
            re.I,
        )
        return match.group(1).strip() if match and match.group(1).strip() else None

    @staticmethod
    def _metric_key(value: str) -> str:
        normalized = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "_", value.casefold()).strip("_")
        return normalized[:140] or new_id()

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        if left in right or right in left:
            return min(len(left), len(right)) / max(len(left), len(right)) + 0.18
        return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _unique(items: list[LearnedMetricDefinition]) -> list[LearnedMetricDefinition]:
        return list({item.id: item for item in items}.values())

    @staticmethod
    def _view(row: LearnedMetricRow) -> LearnedMetricDefinition:
        return LearnedMetricDefinition(
            id=row.id,
            owner_id=row.owner_id,
            metric_key=row.metric_key,
            display_name=row.display_name,
            aliases=json.loads(row.aliases_json),
            version=row.version,
            status=row.status,
            definition=ControlledMetricSpec.model_validate_json(row.definition_json),
            source=row.source,
            created_at=row.created_at.isoformat(),
        )
