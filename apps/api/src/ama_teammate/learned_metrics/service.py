from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from sqlalchemy import select

from ama_teammate.data_access.models import DataSourceConfig
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.domain.models import new_id, utc_now
from ama_teammate.learned_metrics.models import (
    ControlledMetricSpec,
    LearnedMetricAmbiguousError,
    LearnedMetricDefinition,
    MetricFilter,
    MetricLearningInputError,
    MetricLearningRequired,
)
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
        self, database: Database, registry: ConnectorRegistry, repository: Repository
    ) -> None:
        self.database = database
        self.registry = registry
        self.repository = repository

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
        combined = normalize_term(f"{context}\n{question}")
        exact: list[tuple[int, LearnedMetricDefinition]] = []
        ranked: list[tuple[float, LearnedMetricDefinition]] = []
        for definition in definitions:
            aliases = {definition.display_name, definition.metric_key, *definition.aliases}
            normalized = {normalize_term(alias) for alias in aliases if normalize_term(alias)}
            contained = [alias for alias in normalized if alias in current or alias in combined]
            if contained:
                exact.append((max(len(alias) for alias in contained), definition))
            ranked.append(
                (max(self._similarity(current, alias) for alias in normalized), definition)
            )
        if exact:
            longest = max(length for length, _ in exact)
            matches = self._unique([item for length, item in exact if length == longest])
            if len(matches) > 1:
                raise LearnedMetricAmbiguousError(matches)
            return matches[0]
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        if ranked and ranked[0][0] >= 0.78:
            close = self._unique([item for score, item in ranked if ranked[0][0] - score < 0.06])
            if len(close) > 1:
                raise LearnedMetricAmbiguousError(close)
            return ranked[0][1]
        return None

    def learning_request(self, question: str) -> MetricLearningRequired:
        metric_name = extract_metric_name(question)
        source = self.registry.config("super_agent_uat")
        denied = {item.casefold() for item in source.denied_columns}
        table_summary = "; ".join(
            f"{table}: {', '.join(self._preview_fields(table, catalog, denied))}"
            for table, catalog in source.tables.items()
        )
        is_rate = "rate" in metric_name.casefold() or "率" in metric_name
        example = (
            f"指标名={metric_name}; 表=visit_log; 统计方式=ratio; "
            "统计字段=session_id; 时间字段=start_time; "
            "分子条件=to_agent_flag:yes; 分母条件=全部; 别名=另一个叫法"
            if is_rate
            else (
                f"指标名={metric_name}; 表=visit_log; 统计方式=count_distinct; "
                "统计字段=session_id; 时间字段=start_time; "
                "过滤=to_agent_flag:yes; 别名=另一个叫法"
            )
        )
        prompt = (
            f"我还不能唯一确定“{metric_name}”怎么算。请告诉我使用哪张表、统计字段和统计方式；"
            "自然语言说明即可。若是比率，请说明分子条件，以及分母是否为全部记录。"
            f"可查询字段预览（已排除禁止字段）— {table_summary}。"
            "我会先验证字段，再把 SQL 给你审批；确认后保存版本，下次相近叫法会直接复用。"
        )
        return MetricLearningRequired(metric_name, question, prompt, example=example)

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
        named = self._named_parts(text)
        display_name = (
            named.get("metric_name") or named.get("指标名") or named.get("name") or metric_name
        ).strip()
        table = self._resolve_table(source, named.get("table") or named.get("表"), text)
        value_field = self._resolve_field(
            source,
            table,
            named.get("value_field") or named.get("统计字段") or named.get("字段"),
            text,
            default=_DEFAULT_FIELDS.get(table, (None, None))[0],
        )
        time_field = self._resolve_field(
            source,
            table,
            named.get("time_field") or named.get("时间字段") or named.get("时间"),
            text,
            default=_DEFAULT_FIELDS.get(table, (None, None))[1],
        )
        aggregation = self._aggregation(
            named.get("aggregation") or named.get("统计方式"), f"{metric_name} {text}"
        )
        filters = self._parse_filters(
            source,
            table,
            named.get("filters")
            or named.get("filter")
            or named.get("过滤")
            or self._natural_part(text, ("过滤条件", "过滤", "filter", "filters"))
            or "",
        )
        numerator = self._parse_filters(
            source,
            table,
            named.get("numerator")
            or named.get("分子条件")
            or named.get("分子")
            or self._natural_part(text, ("分子条件", "分子", "numerator"))
            or "",
        )
        denominator = self._parse_filters(
            source,
            table,
            named.get("denominator")
            or named.get("分母条件")
            or named.get("分母")
            or self._natural_part(text, ("分母条件", "分母", "denominator"))
            or "",
        )
        if aggregation == "ratio" and not numerator:
            raise MetricLearningInputError(
                "A rate needs a numerator condition, for example 分子条件=to_agent_flag:yes."
            )
        dimensions_value = (
            named.get("dimensions")
            or named.get("维度")
            or self._natural_part(text, ("维度", "dimensions", "dimension"))
            or ""
        )
        dimensions = [
            self._resolve_field(source, table, item, item)
            for item in re.split(r"[|/、\s]+", dimensions_value)
            if item.strip()
        ]
        alias_text = (
            named.get("aliases")
            or named.get("别名")
            or self._natural_part(text, ("别名", "aliases", "alias"))
            or ""
        )
        aliases = [
            display_name,
            metric_name,
            extract_metric_name(original_question),
            *[item.strip() for item in re.split(r"[|/、,，]+", alias_text) if item.strip()],
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

    def _parse_filters(
        self, source: DataSourceConfig, table: str, value: str
    ) -> list[MetricFilter]:
        if not value.strip() or value.strip().casefold() in {"all", "all rows", "全部", "无"}:
            return []
        result: list[MetricFilter] = []
        pattern = re.compile(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|!=|=|>|<|:|：)\s*([^|、]+?)"
            r"(?=(?:\s+(?:and|且)\s+|[|、]|$))",
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
            result.append(
                MetricFilter(
                    field=field, operator="=" if operator in {":", "："} else operator, value=parsed
                )
            )
        if not result:
            raise MetricLearningInputError(
                "I could not parse the filter. Use field=value, for example to_agent_flag=yes."
            )
        return result

    @staticmethod
    def _aggregation(explicit: str | None, text: str) -> str:
        value = f"{explicit or ''} {text}".casefold()
        if any(item in value for item in ("ratio", "rate", "率", "比例")):
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
            "Please specify count, count distinct, sum, average, min, max, or rate."
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
