from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ama_teammate.analysis.adhoc import AdHocQueryNeedsClarification
from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.models import (
    AnalysisIntent,
    AnalysisKind,
    ChartKind,
    DataConfidence,
    Dataset,
    DatasetQuality,
)
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
    AdHocQueryRequest,
    ControlledMetricSpec,
    MetricFilter,
    MetricFilterGroup,
)
from ama_teammate.learned_metrics.service import LearnedMetricService
from ama_teammate.services.analysis import AnalysisService
from ama_teammate.sql_policy.gateway import SQLSafetyGateway


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
                        ColumnCatalog(name="date", data_type="date"),
                        ColumnCatalog(name="source", data_type="varchar"),
                        ColumnCatalog(name="is_device_switch", data_type="boolean"),
                        ColumnCatalog(name="is_cid", data_type="varchar"),
                        ColumnCatalog(name="intent_type", data_type="varchar"),
                        ColumnCatalog(name="eticket_case_number", data_type="varchar"),
                        ColumnCatalog(name="msd_case_number", data_type="varchar"),
                        ColumnCatalog(name="pd_triggered", data_type="varchar"),
                        ColumnCatalog(name="survey_score", data_type="varchar"),
                        ColumnCatalog(name="channel", data_type="varchar"),
                        ColumnCatalog(name="chat_log_text", data_type="string"),
                    ],
                ),
                "turn_log": TableCatalog(
                    name="turn_log",
                    columns=[
                        ColumnCatalog(name="turn_id", data_type="varchar"),
                        ColumnCatalog(name="session_id", data_type="varchar"),
                        ColumnCatalog(name="start_time", data_type="datetime"),
                        ColumnCatalog(name="intent_type", data_type="varchar"),
                        ColumnCatalog(name="flow_id", data_type="varchar"),
                        ColumnCatalog(name="flow_step", data_type="varchar"),
                    ],
                ),
                "telemetry_log": TableCatalog(
                    name="telemetry_log",
                    columns=[
                        ColumnCatalog(name="event_id", data_type="varchar"),
                        ColumnCatalog(name="session_id", data_type="varchar"),
                        ColumnCatalog(name="timestamp", data_type="datetime"),
                        ColumnCatalog(name="event_name", data_type="varchar"),
                    ],
                ),
            },
        )

    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            source_id="super_agent_uat", ok=True, safe_message="test", latency_ms=0
        )

    async def execute(self, request: QueryExecutionRequest) -> QueryExecutionResult:
        raise AssertionError(f"Planner test must not execute SQL: {request.sql}")

    async def close(self) -> None:
        return None


def _planner(client: TestClient) -> AnalysisPlanner:
    registry = ConnectorRegistry([CatalogOnlyConnector()])
    learned = LearnedMetricService(
        client.app.state.database,
        registry,
        client.app.state.repository,
        client.app.state.semantic_metadata_registry,
    )
    return AnalysisPlanner(
        client.app.state.providers,
        registry,
        SQLSafetyGateway(),
        client.app.state.semantic_metadata_registry,
        client.app.state.analysis_skill_registry,
        learned,
    )


async def _plan(client: TestClient, question: str) -> dict[str, Any]:
    plan = await _planner(client).build("ad-hoc-run", question, owner_id="local-dev-user")
    return AnalysisService.safe_plan(plan)


@pytest.mark.asyncio
async def test_explicit_ratio_overrides_historical_cid_rate(client: TestClient) -> None:
    plan = await _plan(
        client,
        "UAT ratio: denominator is sessions where is_cid='1'; numerator is those "
        "sessions where eticket_case_number is not null.",
    )
    query = plan["queries"][0]
    sql = str(query["sql"])
    parameters = query["parameters"]

    assert plan["metric"] == "CID sessions with a created case rate"
    assert "is_cid = :denominator_0" in sql
    assert "eticket_case_number" in sql and (
        "IS NOT NULL" in sql or "NOT eticket_case_number IS NULL" in sql
    )
    assert "AS visitors" in sql and "AS conversions" in sql
    assert parameters["denominator_0"] == "1"


@pytest.mark.asyncio
async def test_cid_case_count_is_not_forced_into_a_rate(client: TestClient) -> None:
    plan = await _plan(client, "UAT count CID sessions that successfully created a case")
    query = plan["queries"][0]
    sql = str(query["sql"])

    assert plan["metric"] == "CID sessions with a created case"
    assert "COUNT(DISTINCT session_id) AS value" in sql
    assert "is_cid = :filter_0" in sql
    assert "eticket_case_number" in sql and (
        "IS NOT NULL" in sql or "NOT eticket_case_number IS NULL" in sql
    )
    assert "AS visitors" not in sql


@pytest.mark.asyncio
async def test_chat_log_text_review_uses_explicit_bounded_fields(client: TestClient) -> None:
    plan = await _plan(client, "UAT review 10 rows of visit_log chat_log_text where is_cid='1'")
    query = plan["queries"][0]
    sql = str(query["sql"])

    assert plan["analysis_type"] == "detail"
    assert "`session_id`, `start_time`, `chat_log_text`" in sql
    assert sql.count("`session_id`") == 1
    assert sql.count("`start_time`") == 4
    assert "is_cid = :detail_0" in sql
    assert query["max_rows"] == 10
    assert "SELECT *" not in sql


@pytest.mark.asyncio
async def test_chinese_explicit_ratio_and_daily_grain_are_preserved(
    client: TestClient,
) -> None:
    question = (
        "\u5206\u6bcd\u662fis_cid='1'\u7684sessions\uff0c"
        "\u5206\u5b50\u662f\u8fd9\u4e9bsessions\u4e2d"
        "eticket_case_number\u4e0d\u4e3a\u7a7a\u7684session\u6570\u91cf\uff0c"
        "\u8ba1\u7b97\u6bd4\u4f8b\u5e76\u6309\u5929\u770b"
    )
    plan = await _plan(client, question)
    sql = str(plan["queries"][0]["sql"])

    assert plan["chart_type"] == "line"
    assert "CAST(start_time AS DATE) AS period" in sql
    assert "GROUP BY CAST(start_time AS DATE)" in sql
    assert "AS visitors" in sql and "AS conversions" in sql and "AS value" in sql


@pytest.mark.asyncio
async def test_controlled_query_supports_multiple_dimensions(client: TestClient) -> None:
    planner = _planner(client)
    spec = ControlledMetricSpec(
        table="visit_log",
        aggregation="count_distinct",
        value_field="session_id",
        time_field="start_time",
        time_grain="month",
        dimensions=["channel", "survey_score"],
    )
    request = AdHocQueryRequest(
        mode="metric",
        display_name="Sessions by month channel and survey score",
        calculation=spec,
    )
    intent = planner.ad_hoc_interpreter._to_intent(
        planner.registry.config("super_agent_uat"), request, "UAT grouped sessions"
    )
    proposal = planner._resolve_controlled_metric_query(intent)

    assert "EXTRACT(YEAR FROM start_time) * 100" in proposal.sql
    assert "EXTRACT(MONTH FROM start_time)" in proposal.sql
    assert "channel, survey_score" in proposal.sql
    assert "GROUP BY" in proposal.sql
    planner.gateway.validate(proposal, planner.registry.config("super_agent_uat"))


def test_model_generated_unknown_field_requires_clarification(client: TestClient) -> None:
    planner = _planner(client)
    request = AdHocQueryRequest(
        mode="metric",
        display_name="Invented metric",
        calculation=ControlledMetricSpec(
            table="visit_log",
            aggregation="count_distinct",
            value_field="session_id",
            time_field="start_time",
            filters=[MetricFilter(field="invented_field", operator="=", value="yes")],
        ),
    )

    with pytest.raises(AdHocQueryNeedsClarification, match="invented_field"):
        planner.ad_hoc_interpreter._to_intent(
            planner.registry.config("super_agent_uat"), request, "UAT invented metric"
        )


def test_filter_compiler_supports_null_between_and_or_groups() -> None:
    parameters: dict[str, str | int | float | bool | None] = {}
    clauses = AnalysisPlanner._compile_filters(
        [
            MetricFilter(field="eticket_case_number", operator="is_not_null"),
            MetricFilter(field="survey_score", operator="between", value=[8, 10]),
            MetricFilter(field="channel", operator="not_in", value=["test", "unknown"]),
        ],
        parameters,
        "condition",
    )
    groups = AnalysisPlanner._compile_filter_groups(
        [
            MetricFilterGroup(filters=[MetricFilter(field="is_cid", operator="=", value="1")]),
            MetricFilterGroup(
                filters=[MetricFilter(field="pd_triggered", operator="=", value="yes")]
            ),
        ],
        parameters,
        "alternative",
    )

    assert clauses[0] == "eticket_case_number IS NOT NULL"
    assert "survey_score BETWEEN :condition_1_low AND :condition_1_high" in clauses
    assert "channel NOT IN (:condition_2_0, :condition_2_1)" in clauses
    assert groups == ["((is_cid = :alternative_0_0) OR (pd_triggered = :alternative_1_0))"]
    assert parameters == {
        "condition_1_low": 8,
        "condition_1_high": 10,
        "condition_2_0": "test",
        "condition_2_1": "unknown",
        "alternative_0_0": "1",
        "alternative_1_0": "yes",
    }


def test_controlled_engine_prepares_bounded_untrusted_text_review() -> None:
    dataset = Dataset(
        id="dataset-1",
        source_ids=["super_agent_uat"],
        query_proposal_ids=["query-1"],
        columns=["session_id", "start_time", "chat_log_text"],
        rows=[
            {"session_id": "a", "start_time": "2026-07-01", "chat_log_text": "first"},
            {"session_id": "b", "start_time": "2026-07-02", "chat_log_text": "first"},
            {"session_id": "c", "start_time": "2026-07-03", "chat_log_text": "second"},
        ],
        row_count=3,
        result_bytes=100,
        quality=DatasetQuality(
            row_count=3,
            missing_by_column={},
            duplicate_rows=0,
            confidence=DataConfidence.HIGH,
        ),
    )
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.DETAIL,
        metric="Bounded chat log text review",
        source_ids=["super_agent_uat"],
        chart_type=ChartKind.TABLE,
        success_criteria="Review the bounded sample.",
        detail_table="visit_log",
        detail_fields=["session_id", "start_time", "chat_log_text"],
        detail_limit=20,
    )

    computation = ControlledAnalysisEngine().analyze(intent, dataset, None)
    review = computation.summary["source_text_review"]

    assert review["trust"] == "untrusted_source_data"
    assert review["rows_reviewed"] == 3
    assert review["duplicate_text_rows"] == 1

    assert review["source_text_samples"] == ["first", "first", "second"]


@pytest.mark.asyncio
async def test_cross_grain_detail_selects_visit_sessions_before_returning_turn_rows(
    client: TestClient,
) -> None:
    plan = await _plan(
        client,
        "UAT 716-719 switch_device\u6210\u529f\u7684sessions\uff0c"
        "\u4eceturn_log\u5bfc\u51fa\u8fd9\u4e9bsession\u7684\u5168\u90e8\u5185\u5bb9",
    )

    query = plan["queries"][0]
    sql = str(query["sql"])

    assert plan["analysis_type"] == "detail"
    assert plan["metric"] == "turn_log rows for selected visit_log entities"
    assert query["parameters"]["start_date"] == "2026-07-16"
    assert query["parameters"]["end_date"] == "2026-07-20"
    assert query["parameters"]["cohort_0"] is True
    assert "FROM `turn_log`" in sql
    assert "COUNT(" not in sql
    assert "`session_id` IN (SELECT DISTINCT `session_id` FROM `visit_log`" in sql
    assert "`is_device_switch` = :cohort_0" in sql or "is_device_switch = :cohort_0" in sql
    assert "ORDER BY `session_id`, `start_time`" in sql
    assert "`date` >= :start_date" in sql
    assert "SELECT *" not in sql
    assert plan["relationship_definitions"] == [
        {
            "definition_type": "relationship",
            "id": "super_agent_uat.visit_to_turn",
            "version": "1.0.0",
        }
    ]


@pytest.mark.asyncio
async def test_case_journey_planning_retrieves_skill_and_compiles_session_safe_sql(
    client: TestClient,
) -> None:
    plan = await _plan(
        client,
        "Super Agent 7\u67085\u65e5\u5efa\u5355\u91cf\u4e0b\u964d\uff0c"
        "\u770b\u770b\u7528\u6237\u79bb\u5f00\u5728\u54ea\u4e2aagent\u9636\u6bb5",
    )

    query = plan["queries"][0]
    sql = str(query["sql"])
    assert plan["analysis_type"] == "journey_diagnostic"
    assert query["parameters"]["start_date"] == "2026-07-02"
    assert query["parameters"]["incident_start"] == "2026-07-05"
    assert query["parameters"]["end_date"] == "2026-07-06"
    assert "ROW_NUMBER() OVER" in sql
    assert "PARTITION BY t.session_id" in sql
    assert "eticket_case_number" in sql
    assert "msd_case_number" in sql
    assert "GROUP BY comparison_window, exit_stage" in sql
    assert any(
        item["skill"]["id"] == "case_journey_diagnostics" for item in plan["skill_execution_plan"]
    )
    assert "COUNT(exit_stage) AS value" in sql
    assert "source = 'pcs-redirect'" in sql
    assert plan["business_rule_definitions"] == [
        {
            "definition_type": "business_rule",
            "id": "super_agent.valid_user_traffic_population",
            "version": "1.0.0",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "table"),
    [
        ("How many Super Agent UAT turns are there in total?", "turn_log"),
        ("How many Super Agent UAT telemetry events are there in total?", "telemetry_log"),
    ],
)
async def test_non_visit_queries_inherit_visit_population_rule(
    client: TestClient, question: str, table: str
) -> None:
    plan = await _plan(client, question)
    sql = str(plan["queries"][0]["sql"])

    assert f"FROM {table}" in sql
    assert "session_id IN (SELECT traffic_scope.session_id FROM visit_log" in sql
    assert "traffic_scope.source = 'pcs-redirect'" in sql
    assert "traffic_scope.channel" in sql
