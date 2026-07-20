from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from ama_teammate.analysis.planner import AnalysisPlanner
from ama_teammate.data_access.models import (
    ColumnCatalog,
    ConnectorHealth,
    DatabaseDialect,
    DataSourceConfig,
    QueryExecutionRequest,
    QueryExecutionResult,
    TableCatalog,
)
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.learned_metrics.models import (
    LearnedMetricAmbiguousError,
    MetricLearningRequired,
)
from ama_teammate.learned_metrics.service import LearnedMetricService
from ama_teammate.providers.base import (
    ModelProfile,
    ProviderMessage,
    SmokeTestResult,
    StructuredProviderRequest,
)
from ama_teammate.providers.factory import ProviderBundle
from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry
from ama_teammate.sql_policy.gateway import SQLSafetyGateway
from ama_teammate.storage.database import Database
from ama_teammate.storage.repositories import Repository


def loaded_semantic_registry() -> SemanticMetadataRegistry:
    registry, issues = SemanticMetadataRegistry.load(Path("knowledge"))
    assert issues == []
    return registry


class CatalogOnlyConnector:
    def __init__(self) -> None:
        self.config = DataSourceConfig(
            id="super_agent_uat",
            display_name="Super Agent UAT",
            dialect=DatabaseDialect.MYSQL,
            execution_dialect="mysql",
            secret_ref="test-only",
            tables={
                "visit_log": TableCatalog(
                    name="visit_log",
                    columns=[
                        ColumnCatalog(name="session_id", data_type="varchar"),
                        ColumnCatalog(name="start_time", data_type="datetime"),
                        ColumnCatalog(name="source", data_type="varchar"),
                        ColumnCatalog(name="to_agent_flag", data_type="varchar"),
                        ColumnCatalog(name="is_foc", data_type="varchar"),
                        ColumnCatalog(name="is_cid", data_type="varchar"),
                        ColumnCatalog(name="deliver_type", data_type="varchar"),
                        ColumnCatalog(name="downgrade_depot", data_type="varchar"),
                        ColumnCatalog(name="channel", data_type="varchar"),
                        ColumnCatalog(name="raw_prompt", data_type="text"),
                    ],
                ),
                "turn_log": TableCatalog(
                    name="turn_log",
                    columns=[
                        ColumnCatalog(name="turn_id", data_type="varchar"),
                        ColumnCatalog(name="start_time", data_type="datetime"),
                    ],
                ),
                "telemetry_log": TableCatalog(
                    name="telemetry_log",
                    columns=[
                        ColumnCatalog(name="event_id", data_type="varchar"),
                        ColumnCatalog(name="timestamp", data_type="datetime"),
                        ColumnCatalog(name="event_name", data_type="varchar"),
                    ],
                ),
            },
            denied_columns={"raw_prompt"},
        )

    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(source_id=self.config.id, ok=True, safe_message="test", latency_ms=0)

    async def execute(self, request: QueryExecutionRequest) -> QueryExecutionResult:
        raise AssertionError(f"Unit test must not execute SQL: {request.sql}")

    async def close(self) -> None:
        return None


class FailingProvider:
    name = "must-not-be-called"

    async def generate_structured(
        self,
        messages: Sequence[ProviderMessage],
        profile: ModelProfile,
        request: StructuredProviderRequest,
    ) -> Any:
        raise AssertionError(
            f"Provider should not be called for learned UAT metadata: {profile.name}/{request.name}"
        )

    def stream(
        self, messages: Sequence[ProviderMessage], profile: ModelProfile
    ) -> AsyncIterator[Any]:
        async def empty() -> AsyncIterator[Any]:
            if False:
                yield None

        return empty()

    async def smoke_test(self, profile: ModelProfile) -> SmokeTestResult:
        raise AssertionError(profile.name)

    async def close(self) -> None:
        return None


@pytest.fixture
async def learned_runtime(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, Repository, ConnectorRegistry, LearnedMetricService]]:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'learned.db'}")
    await database.initialize()
    repository = Repository(database)
    await repository.ensure_user("user-1", "Test User")
    registry = ConnectorRegistry([CatalogOnlyConnector()])
    semantic_registry, issues = SemanticMetadataRegistry.load(Path("knowledge"))
    assert issues == []
    service = LearnedMetricService(database, registry, repository, semantic_registry)
    try:
        yield database, repository, registry, service
    finally:
        await registry.close()
        await database.close()


async def teach_handoff_rate(service: LearnedMetricService) -> None:
    await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="Agent Handoff Rate",
        original_question="SA Agent Handoff Rate 是多少",
        clarification=(
            "指标名=Agent Handoff Rate; 表=visit_log; 统计方式=ratio; "
            "统计字段=session_id; 时间字段=start_time; "
            "分子条件=to_agent_flag:yes; 别名=转人工率|handoff rate"
        ),
        session_id="session-1",
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_explicit_definition_persists_and_tolerates_alias_typo(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    database, repository, registry, service = learned_runtime
    await teach_handoff_rate(service)

    resolved = await LearnedMetricService(database, registry, repository).resolve(
        "user-1", "SA agent handof rate 目前是多少"
    )

    assert resolved is not None
    assert resolved.display_name == "Agent Handoff Rate"
    assert resolved.definition.table == "visit_log"
    assert resolved.definition.numerator_filters[0].field == "to_agent_flag"
    assert resolved.definition.numerator_filters[0].value == "yes"


@pytest.mark.asyncio
async def test_natural_language_definition_is_parsed(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    learned = await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="Transfer Session Count",
        original_question="SA 转人工 session 有多少",
        clarification=(
            "用 visit_log 的 session_id 去重计数，时间用 start_time，"
            "过滤 to_agent_flag=yes，别名叫转人工会话|transfer sessions"
        ),
        session_id="session-1",
        run_id="run-2",
    )

    assert learned.definition.aggregation == "count_distinct"
    assert learned.definition.filters[0].field == "to_agent_flag"
    assert "转人工会话" in learned.aliases


@pytest.mark.asyncio
async def test_natural_ratio_condition_maps_logical_true_to_physical_value(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    learned = await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="CID Session Rate",
        original_question="能看到数据里目前cid的session占比多少吗",
        clarification=(
            "is_cid is true的比例\nis_cid这个字段取值为true的就是CID的case，就是用户自损的情况"
        ),
        session_id="session-1",
        run_id="run-cid",
    )

    assert learned.definition.table == "visit_log"
    assert learned.definition.aggregation == "ratio"
    assert learned.definition.value_field == "session_id"
    assert learned.definition.numerator_filters[0].field == "is_cid"
    assert learned.definition.numerator_filters[0].value == "1"


@pytest.mark.asyncio
async def test_targeted_answer_reuses_field_and_table_from_original_question(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    learned = await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="CID Share",
        original_question="is_cid 的占比",
        clarification="true 算命中，分母是全部会话",
        session_id="session-1",
        run_id="run-targeted-cid",
    )

    assert learned.definition.table == "visit_log"
    assert learned.definition.value_field == "session_id"
    assert learned.definition.numerator_filters[0].field == "is_cid"
    assert learned.definition.numerator_filters[0].value == "1"


def test_known_physical_field_gets_targeted_learning_question(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    request = service.learning_request("is_cid 的占比")
    assert request.missing_fields == ["numerator_value", "denominator_scope"]
    assert "visit_log.is_cid" in request.prompt
    assert "什么值算命中" in request.prompt


def test_unknown_rate_asks_for_business_population_instead_of_machine_template(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    request = service.learning_request(
        "how many percent of onsite customer would accept downgrade to depot"
    )

    assert request.missing_fields == [
        "denominator_population",
        "numerator_condition",
    ]
    assert "不需要写 field=value" in request.prompt
    assert "visit_log.downgrade_depot" in request.prompt
    assert "分母是 deliver type 为 onsite" in request.example


@pytest.mark.asyncio
async def test_detailed_business_narrative_becomes_executable_ratio(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    question = "how many percent of onsite customer would accept downgrade to depot"
    clarification = (
        "deliver type这个字段就是用户的交付类型，onsite是其中的一种，上门服务，"
        "depot也是其中的一种寄修。accept downgrade这个字段是记录是否同意降级成"
        "depot服务的。分母是全部的onsite用户sessions，"
        "分子是accept downgraded的sessions数量"
    )

    learned = await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="percent of onsite customer would accept downgrade to depot",
        original_question=question,
        clarification=clarification,
        session_id="session-1",
        run_id="run-onsite-downgrade",
    )

    assert learned.definition.table == "visit_log"
    assert learned.definition.aggregation == "ratio"
    assert learned.definition.value_field == "session_id"
    assert learned.definition.denominator_filters[0].field == "deliver_type"
    assert learned.definition.denominator_filters[0].operator == "="
    assert learned.definition.denominator_filters[0].value == "on-site"
    assert learned.definition.numerator_filters[0].field == "downgrade_depot"
    assert learned.definition.numerator_filters[0].operator == "="
    assert learned.definition.numerator_filters[0].value == "yes"

    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        loaded_semantic_registry(),
        learned_metrics=service,
    )
    plan = await planner.build(
        "run-onsite-downgrade-plan",
        question,
        owner_id="user-1",
        context="Super Agent UAT",
    )
    sql = plan.queries[0].normalized_sql.upper()
    assert "DELIVER_TYPE = :DENOMINATOR_0" in sql
    assert "DOWNGRADE_DEPOT = :NUMERATOR_0" in sql
    assert plan.queries[0].parameters["denominator_0"] == "on-site"
    assert plan.intent.metadata_confidence == "learned_definition"


def test_explicit_field_filter_defaults_to_distinct_dataset_entity(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    inferred = service.infer_field_query(
        "user-1", "\u53ea\u8981 downgrade_depot=yes \u7684 session"
    )

    assert inferred is not None
    assert inferred.source == "Approved field metadata and deterministic physical query"
    assert inferred.definition.table == "visit_log"
    assert inferred.definition.aggregation == "count_distinct"
    assert inferred.definition.value_field == "session_id"
    assert inferred.definition.filters[0].field == "downgrade_depot"
    assert inferred.definition.filters[0].value == "yes"


def test_field_distribution_can_reuse_field_from_conversation_context(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    inferred = service.infer_field_query(
        "user-1",
        "\u4f60\u5148\u770b\u8fd9\u4e2a\u5b57\u6bb5\u7684\u53d6\u503c\u5206\u5e03",
        context="\u5b57\u6bb5\u540d\u662f downgrade_depot",
    )

    assert inferred is not None
    assert inferred.definition.dimensions == ["downgrade_depot"]
    assert inferred.definition.filters == []


def test_business_value_alias_normalizes_to_approved_physical_value(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime

    inferred = service.infer_field_query("user-1", "deliver_type=onsite session \u6570")

    assert inferred is not None
    assert inferred.definition.filters[0].value == "on-site"


@pytest.mark.asyncio
async def test_field_query_planning_retrieves_field_metadata_before_sql(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    semantic_registry, issues = SemanticMetadataRegistry.load(Path("knowledge"))
    assert issues == []
    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        semantic_registry,
        learned_metrics=service,
    )

    plan = await planner.build(
        "run-field-count",
        "\u53ea\u8981 downgrade_depot=yes \u7684 session",
        owner_id="user-1",
        context="Super Agent UAT",
    )

    assert plan.metric_definition.definition_type.value == "field"
    assert plan.metric_definition.id == "super_agent_uat.visit_log.downgrade_depot"
    assert plan.metric_definition.version == "1.0.0"
    assert "COUNT(DISTINCT session_id)" in plan.queries[0].normalized_sql
    assert plan.queries[0].parameters["filter_0"] == "yes"


@pytest.mark.asyncio
async def test_field_distribution_plans_grouping_without_aggregation_question(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    semantic_registry, issues = SemanticMetadataRegistry.load(Path("knowledge"))
    assert issues == []
    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        semantic_registry,
        learned_metrics=service,
    )

    plan = await planner.build(
        "run-field-distribution",
        "\u770b\u8fd9\u4e2a\u5b57\u6bb5\u7684\u53d6\u503c\u5206\u5e03",
        owner_id="user-1",
        context="\u524d\u9762\u786e\u8ba4\u7684\u5b57\u6bb5\u662f downgrade_depot",
    )

    assert plan.intent.analysis_type.value == "segment_breakdown"
    assert plan.intent.dimensions == ["downgrade_depot"]
    assert "GROUP BY downgrade_depot" in plan.queries[0].normalized_sql
    assert plan.intent.chart_type.value == "bar"


@pytest.mark.asyncio
async def test_shared_alias_is_ambiguous_instead_of_guessed(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime
    for index, field in enumerate(("to_agent_flag", "is_foc"), start=1):
        await service.learn_from_clarification(
            owner_id="user-1",
            metric_name=f"Quality Metric {index}",
            original_question=f"SA Quality Metric {index}",
            clarification=(
                f"指标名=Quality Metric {index}; 表=visit_log; 统计方式=ratio; "
                f"统计字段=session_id; 时间字段=start_time; 分子条件={field}:yes; "
                "别名=quality rate"
            ),
            session_id="session-1",
            run_id=f"run-{index}",
        )

    with pytest.raises(LearnedMetricAmbiguousError):
        await service.resolve("user-1", "SA quality rate 是多少")


@pytest.mark.asyncio
async def test_sql_planning_retrieves_learned_metadata_before_model(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    await teach_handoff_rate(service)
    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        loaded_semantic_registry(),
        learned_metrics=service,
    )

    plan = await planner.build(
        "run-plan",
        "SA agent handoff rate 目前是多少",
        owner_id="user-1",
    )

    assert plan.intent.metadata_confidence == "learned_definition"
    assert plan.metric_definition.id.startswith("learned.metric_")
    assert plan.metric_definition.version == "1.0.0"
    assert "TO_AGENT_FLAG = :NUMERATOR_0" in plan.queries[0].normalized_sql.upper()
    assert plan.queries[0].parameters["numerator_0"] == "yes"


@pytest.mark.asyncio
async def test_unknown_uat_metric_asks_for_fields_without_model(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        loaded_semantic_registry(),
        learned_metrics=service,
    )

    with pytest.raises(MetricLearningRequired) as raised:
        await planner.build("run-unknown", "SA 的 Good Session Rate 是多少", owner_id="user-1")

    assert raised.value.metric_name == "Good Session Rate"
    assert "分母是哪些 sessions" in raised.value.prompt
    assert "分子在这些 sessions" in raised.value.prompt
    assert "field=value" in raised.value.prompt
    assert "raw_prompt" not in raised.value.prompt
    assert raised.value.missing_fields == [
        "denominator_population",
        "numerator_condition",
    ]


@pytest.mark.asyncio
async def test_explicit_correction_creates_new_version_and_reenters_teaching(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, registry, service = learned_runtime
    await teach_handoff_rate(service)
    profile = ModelProfile(name="unused", deployment="unused")
    planner = AnalysisPlanner(
        ProviderBundle(
            provider=cast(Any, FailingProvider()),
            coordinator=profile,
            analyst=profile,
            curator=profile,
        ),
        registry,
        SQLSafetyGateway(),
        loaded_semantic_registry(),
        learned_metrics=service,
    )

    with pytest.raises(MetricLearningRequired) as raised:
        await planner.build(
            "run-correction",
            "SA 修改 Agent Handoff Rate 定义",
            owner_id="user-1",
        )
    assert raised.value.metric_name == "Agent Handoff Rate"

    corrected = await service.learn_from_clarification(
        owner_id="user-1",
        metric_name=raised.value.metric_name,
        original_question=raised.value.question,
        clarification=(
            "指标名=Agent Handoff Rate; 表=visit_log; 统计方式=ratio; "
            "统计字段=session_id; 时间字段=start_time; 分子条件=is_foc:yes; "
            "别名=转人工率|handoff rate"
        ),
        session_id="session-1",
        run_id="run-correction",
    )

    active = await service.list_active("user-1")
    assert corrected.version == 2
    assert len(active) == 1
    assert active[0].definition.numerator_filters[0].field == "is_foc"


@pytest.mark.asyncio
async def test_explicit_current_metric_beats_stale_learned_context(
    learned_runtime: tuple[Database, Repository, ConnectorRegistry, LearnedMetricService],
) -> None:
    _, _, _, service = learned_runtime
    await service.learn_from_clarification(
        owner_id="user-1",
        metric_name="Traffic",
        original_question="Super Agent UAT traffic",
        clarification=(
            "metric_name=Traffic; table=visit_log; aggregation=count_distinct; "
            "value_field=session_id; time_field=start_time"
        ),
        session_id="session-1",
        run_id="run-traffic",
    )

    resolved = await service.resolve(
        "user-1",
        "case creation rate daily trend",
        context="Earlier approved plan used Traffic daily trend.",
    )

    assert resolved is None
