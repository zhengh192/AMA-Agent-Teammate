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
                        ColumnCatalog(name="to_agent_flag", data_type="varchar"),
                        ColumnCatalog(name="is_foc", data_type="varchar"),
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
    service = LearnedMetricService(database, registry, repository)
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
        cast(SemanticMetadataRegistry, object()),
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
        cast(SemanticMetadataRegistry, object()),
        learned_metrics=service,
    )

    with pytest.raises(MetricLearningRequired) as raised:
        await planner.build("run-unknown", "SA 的 Good Session Rate 是多少", owner_id="user-1")

    assert raised.value.metric_name == "Good Session Rate"
    assert "visit_log" in raised.value.prompt
    assert "session_id" in raised.value.prompt
    assert "raw_prompt" not in raised.value.prompt
    assert "统计方式=ratio" in raised.value.example


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
        cast(SemanticMetadataRegistry, object()),
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
