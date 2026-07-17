from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from ama_teammate.analysis.models import AnalysisIntent, JoinPlan
from ama_teammate.analysis.planner import AnalysisPlanner
from ama_teammate.config import Settings
from ama_teammate.data_access.demo import DemoReadOnlyConnector, demo_source_configs
from ama_teammate.data_access.models import (
    ColumnCatalog,
    DatabaseDialect,
    DataSourceConfig,
    TableCatalog,
)
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.providers.factory import create_provider_bundle
from ama_teammate.semantic_metadata.models import (
    DefinitionStatus,
    DefinitionType,
    FieldDefinition,
    MetricDefinition,
    ResolvedAnalysisMetadata,
)
from ama_teammate.semantic_metadata.registry import (
    MetadataAmbiguousError,
    SemanticMetadataRegistry,
)
from ama_teammate.sql_policy.gateway import SQLSafetyGateway
from ama_teammate.sql_policy.models import QueryProposal

ROOT = Path(__file__).parents[3]


def loaded_registry() -> SemanticMetadataRegistry:
    registry, issues = SemanticMetadataRegistry.load(ROOT / "knowledge")
    assert issues == []
    return registry


def test_repository_yaml_validates_and_strict_schema_rejects_unknown_fields() -> None:
    registry = loaded_registry()
    assert len(registry.list_definitions()) >= 100
    field = registry.get(DefinitionType.FIELD, "super_agent.session.logged_in")
    assert isinstance(field, FieldDefinition)
    invalid = field.model_dump()
    invalid["unapproved_attribute"] = "not allowed"
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate(invalid)


def test_ambiguous_active_metric_alias_requires_clarification() -> None:
    registry = loaded_registry()
    revenue = registry.get(DefinitionType.METRIC, "demo.revenue")
    assert isinstance(revenue, MetricDefinition)
    first = revenue.model_copy(
        update={"id": "test.booked_revenue", "name": "Booked Revenue", "aliases": ["shared total"]}
    )
    second = revenue.model_copy(
        update={"id": "test.billed_revenue", "name": "Billed Revenue", "aliases": ["shared total"]}
    )
    ambiguous = SemanticMetadataRegistry([*registry.list_definitions(), first, second])
    with pytest.raises(MetadataAmbiguousError) as exc_info:
        ambiguous.resolve_metric("shared total")
    assert {item.id for item in exc_info.value.matches} == {
        "test.booked_revenue",
        "test.billed_revenue",
    }
    assert ambiguous.resolve_metric(
        "shared total", context="Use test.booked_revenue"
    ).id == "test.booked_revenue"


@pytest.mark.asyncio
async def test_sql_planning_retrieves_metadata_first(tmp_path: Path) -> None:
    events: list[str] = []
    base = loaded_registry()

    class TrackingRegistry(SemanticMetadataRegistry):
        def resolve_analysis_metadata(
            self,
            metric_term: str,
            dimensions: list[str],
            *,
            context: str,
            connectors: ConnectorRegistry,
        ) -> ResolvedAnalysisMetadata:
            events.append("metadata")
            return super().resolve_analysis_metadata(
                metric_term, dimensions, context=context, connectors=connectors
            )

    class TrackingPlanner(AnalysisPlanner):
        def _resolve_queries(
            self, intent: AnalysisIntent
        ) -> tuple[list[QueryProposal], JoinPlan | None]:
            events.append("sql")
            return super()._resolve_queries(intent)

    connectors = ConnectorRegistry(
        [
            DemoReadOnlyConnector(config, tmp_path / f"{config.id}.db")
            for config in demo_source_configs()
        ]
    )
    semantic = TrackingRegistry(base.list_definitions())
    providers = create_provider_bundle(Settings(_env_file=None, ama_provider="mock"))
    planner = TrackingPlanner(providers, connectors, SQLSafetyGateway(), semantic)
    try:
        plan = await planner.build("run-metadata-first", "Show the revenue trend")
    finally:
        await providers.provider.close()
        await connectors.close()
    assert events[:2] == ["metadata", "sql"]
    assert plan.metric_definition.id == "demo.revenue"
    assert plan.metric_definition.version == "1.0.0"


def test_semantic_metadata_api_lists_retrieves_and_searches(client: Any) -> None:
    listed = client.get(
        "/api/semantic-metadata",
        params={"definition_type": "metric", "status": DefinitionStatus.DRAFT.value},
    )
    assert listed.status_code == 200
    assert any(item["id"] == "super_agent.whtr" for item in listed.json())

    retrieved = client.get("/api/semantic-metadata/metric/super_agent.whtr")
    assert retrieved.status_code == 200
    assert retrieved.json()["version"] == "0.9.30"

    searched = client.get("/api/semantic-metadata/search", params={"q": "working hours transfer"})
    assert searched.status_code == 200
    assert searched.json()[0]["id"] == "super_agent.whtr"
@pytest.mark.asyncio
async def test_uat_natural_language_planning_uses_approved_physical_metric() -> None:
    visit_table = TableCatalog(
        name="visit_log",
        columns=[
            ColumnCatalog(name="session_id", data_type="varchar(255)", nullable=True),
            ColumnCatalog(name="start_time", data_type="datetime(6)", nullable=True),
            ColumnCatalog(name="channel", data_type="string", nullable=True),
            ColumnCatalog(name="intent_type", data_type="string", nullable=True),
            ColumnCatalog(name="agent_working_hour", data_type="string", nullable=True),
            ColumnCatalog(name="to_agent_flag", data_type="string", nullable=True),
            ColumnCatalog(name="touchless_exception", data_type="string", nullable=True),
            ColumnCatalog(name="is_foc", data_type="string", nullable=True),
            ColumnCatalog(name="survey_score", data_type="double", nullable=True),
            ColumnCatalog(name="survey_resolved", data_type="string", nullable=True),
        ],
    )
    source = DataSourceConfig(
        id="super_agent_uat",
        display_name="Super Agent UAT",
        dialect=DatabaseDialect.MYSQL,
        execution_dialect="mysql",
        secret_ref="env:super_agent_uat",
        allowed_schemas={"sa_logs"},
        tables={"visit_log": visit_table},
        max_rows=500,
        max_result_bytes=262_144,
    )
    connectors = ConnectorRegistry([SimpleNamespace(config=source)])
    semantic = loaded_registry()
    providers = create_provider_bundle(Settings(_env_file=None, ama_provider="mock"))
    planner = AnalysisPlanner(providers, connectors, SQLSafetyGateway(), semantic)
    context = planner._approved_semantic_context("How many Super Agent UAT sessions are there?")
    assert [item["id"] for item in context["metrics"]] == [
        "super_agent_uat.session_count"
    ]
    try:
        plan = await planner.build("run-uat", "How many Super Agent UAT sessions are there in total?")
    finally:
        await providers.provider.close()

    assert plan.metric_definition.id == "super_agent_uat.session_count"
    assert plan.metric_definition.version == "1.0.0"
    assert plan.intent.source_ids == ["super_agent_uat"]
    assert plan.intent.start_date == "2026-06-01"
    assert plan.intent.end_date == (date.today() + timedelta(days=1)).isoformat()
    assert plan.queries[0].referenced_tables == ["visit_log"]
    assert "COUNT(DISTINCT session_id)" in plan.queries[0].normalized_sql
    assert plan.queries[0].dialect == "mysql"

    working = await planner.build("run-whtr", "Show Super Agent UAT WHTR")
    assert working.metric_definition.id == "super_agent.whtr"
    assert working.metric_definition.version == "0.9.30"
    assert working.intent.metadata_confidence == "working_assumption"
    assert working.intent.assumptions
    assert "agent_working_hour" in working.queries[0].normalized_sql
    assert "to_agent_flag" in working.queries[0].normalized_sql
