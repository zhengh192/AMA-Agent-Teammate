from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ama_teammate.analysis.charts import ChartBuilder, PlotlySpecValidator
from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.models import (
    AnalysisComputation,
    AnalysisIntent,
    AnalysisKind,
    ChartKind,
    Conclusion,
    Dataset,
    DatasetQuality,
)
from ama_teammate.data_access.demo import (
    DemoDatabaseManager,
    DemoReadOnlyConnector,
    demo_source_configs,
)
from ama_teammate.data_access.models import QueryExecutionFailure, QueryExecutionRequest
from ama_teammate.sql_policy.gateway import SQLSafetyGateway
from ama_teammate.sql_policy.models import QueryProposal, SQLPolicyViolation


def parse_sse(lines: Iterator[str]) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event_name = "message"
    for line in lines:
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event_name, json.loads(line.removeprefix("data: "))))
    return events


def create_session(client: TestClient) -> str:
    response = client.post("/api/sessions", json={"title": "Phase 2 demo"})
    assert response.status_code == 201
    return str(response.json()["id"])


def request_plan(client: TestClient, question: str) -> tuple[str, dict[str, object]]:
    session_id = create_session(client)
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"content": question},
    ) as response:
        assert response.status_code == 200
        events = parse_sse(response.iter_lines())
    started = next(data for name, data in events if name == "run.started")
    approval = next(data for name, data in events if name == "approval.required")
    assert approval["status"] == "waiting_approval"
    return str(started["run_id"]), approval


def approve_plan(client: TestClient, run_id: str, approval: dict[str, object]) -> dict[str, object]:
    with client.stream(
        "POST",
        f"/api/runs/{run_id}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": approval["payload_hash"],
            "status": "approved",
            "comment": "Approved for bounded local demo execution.",
        },
    ) as response:
        assert response.status_code == 200
        events = parse_sse(response.iter_lines())
    assert any(name == "run.completed" for name, _ in events)
    return next(data for name, data in events if name == "analysis.result")


def test_connector_registry_health_and_secret_redaction(client: TestClient) -> None:
    response = client.get("/api/data-sources")
    assert response.status_code == 200
    sources = response.json()
    assert {source["id"] for source in sources} == {
        "sales_postgres",
        "marketing_mysql",
        "operations_sqlserver",
    }
    assert {source["dialect"] for source in sources} == {"postgres", "mysql", "tsql"}
    assert all(source["read_only"] is True for source in sources)
    assert all(source["secret_ref"] == "[REDACTED]" for source in sources)
    assert all(source["health"]["ok"] is True for source in sources)


@pytest.mark.parametrize(
    ("sql", "parameters", "code"),
    [
        ("INSERT INTO daily_sales (revenue) VALUES (1)", {}, "read_only_required"),
        (
            "SELECT sale_date FROM daily_sales; SELECT revenue FROM daily_sales",
            {},
            "multiple_statements",
        ),
        ("SELECT customer_email FROM daily_sales", {}, "column_denied"),
        ("SELECT * FROM daily_sales", {}, "wildcard_not_allowed"),
        ("SELECT sale_date FROM private_sales", {}, "table_not_allowed"),
        ("SELECT sale_date FROM daily_sales -- bypass", {}, "comments_not_allowed"),
        ("SELECT PG_SLEEP(1) FROM daily_sales", {}, "function_not_allowed"),
        ("SELECT sale_date INTO backup FROM daily_sales", {}, "write_or_admin"),
    ],
)
def test_sql_ast_gateway_rejects_write_and_bypass(
    sql: str, parameters: dict[str, object], code: str
) -> None:
    source = demo_source_configs()[0]
    proposal = QueryProposal(
        id="proposal",
        source_id=source.id,
        sql=sql,
        parameters=parameters,
        purpose="adversarial test",
        max_rows=100,
        max_result_bytes=10_000,
        timeout_seconds=5,
    )
    with pytest.raises(SQLPolicyViolation) as caught:
        SQLSafetyGateway().validate(proposal, source)
    assert caught.value.code == code


def test_sql_ast_gateway_accepts_read_only_union() -> None:
    source = demo_source_configs()[0]
    proposal = QueryProposal(
        id="union-proposal",
        source_id=source.id,
        sql=(
            "SELECT sale_date AS period, revenue AS value FROM daily_sales "
            "UNION ALL "
            "SELECT sale_date AS period, revenue AS value FROM daily_sales"
        ),
        parameters={},
        purpose="read-only set operation",
        max_rows=100,
        max_result_bytes=10_000,
        timeout_seconds=5,
    )

    validated = SQLSafetyGateway().validate(proposal, source)

    assert "UNION ALL" in validated.normalized_sql
    assert validated.referenced_tables == ["daily_sales"]


def test_single_database_metric_approval_execution_chart_evidence_and_csv(
    client: TestClient,
) -> None:
    run_id, approval = request_plan(
        client, "Query revenue trend for 2025 from the PostgreSQL sales data source."
    )
    plan = approval["plan"]
    assert isinstance(plan, dict)
    assert plan["analysis_type"] == "trend"
    assert plan["queries"][0]["source_id"] == "sales_postgres"
    assert plan["queries"][0]["sql"].upper().startswith("SELECT")
    result = approve_plan(client, run_id, approval)
    assert result["chart"]["chart_type"] == "line"
    final_dataset = result["datasets"][-1]
    assert final_dataset["row_count"] == 12
    evidence_ids = {item["id"] for item in result["computation"]["evidence"]}
    assert evidence_ids
    assert all(
        set(item["evidence_ids"]) <= evidence_ids for item in result["computation"]["conclusions"]
    )
    download = client.get(f"/api/artifacts/{result['csv_artifact_id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert b"period,value,orders" in download.content


def test_scalar_count_is_not_described_as_a_flat_trend() -> None:
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.TREND,
        metric="downgrade_depot=yes session count",
        source_ids=["super_agent_uat"],
        chart_type=ChartKind.KPI,
        success_criteria="Return the bounded scalar count.",
    )
    dataset = Dataset(
        id="dataset-scalar-count",
        source_ids=["super_agent_uat"],
        query_proposal_ids=["query-scalar-count"],
        columns=["value"],
        rows=[{"value": 167}],
        row_count=1,
        result_bytes=20,
        quality=DatasetQuality(row_count=1, missing_by_column={"value": 0}, duplicate_rows=0),
    )

    computation = ControlledAnalysisEngine().analyze(intent, dataset, None)
    chart = ChartBuilder(PlotlySpecValidator()).build(intent, dataset, computation)

    assert computation.summary == {"value": 167.0}
    assert "flat" not in computation.conclusions[0].text.casefold()
    assert computation.conclusions[0].text.endswith("167.")
    assert chart.figure["data"][0]["value"] == 167.0


def test_cross_database_join_records_unmatched_quality(client: TestClient) -> None:
    run_id, approval = request_plan(
        client,
        "Run a data query for revenue by channel across PostgreSQL and MySQL for 2025.",
    )
    result = approve_plan(client, run_id, approval)
    quality = result["join_quality"]
    assert quality["left_rows"] == 3
    assert quality["right_rows"] == 4
    assert quality["matched_left_rows"] == 3
    assert quality["right_unmatched_rate"] == 0.25
    assert quality["type_coercion"] == "string"
    assert quality["weak"] is True


def test_stacked_bar_contribution_is_reproducible(client: TestClient) -> None:
    run_id, approval = request_plan(
        client,
        "Analyze data revenue contribution by segment with a stacked chart for 2025 from PostgreSQL.",
    )
    result = approve_plan(client, run_id, approval)
    assert result["chart"]["chart_type"] == "stacked_bar"
    summary = result["computation"]["summary"]
    assert summary["reconciliation_gap"] == 0
    assert pytest.approx(sum(summary["shares"].values())) == 1


def test_completeness_issue_is_confirmed(client: TestClient) -> None:
    run_id, approval = request_plan(
        client,
        "Analyze conversion rate data completeness, missing and duplicate rows for 2025 from SQL Server.",
    )
    result = approve_plan(client, run_id, approval)
    quality = result["datasets"][-1]["quality"]
    assert quality["duplicate_rows"] >= 1
    assert quality["missing_by_column"]["event_id"] >= 1
    assert quality["missing_by_column"]["conversions"] >= 1


def test_correlation_explanation_is_inferred_not_causal(client: TestClient) -> None:
    run_id, approval = request_plan(
        client,
        "Data query: why is revenue correlated with marketing spend in 2025 using PostgreSQL and MySQL?",
    )
    result = approve_plan(client, run_id, approval)
    conclusions = result["computation"]["conclusions"]
    correlation = next(item for item in conclusions if "correlation" in item["text"])
    assert correlation["epistemic_label"] == "Inferred"
    assert "not a causal effect" in correlation["text"]


def test_approval_payload_change_fails_without_execution(client: TestClient) -> None:
    run_id, approval = request_plan(
        client, "Query revenue trend for 2025 from the PostgreSQL sales data source."
    )
    with client.stream(
        "POST",
        f"/api/runs/{run_id}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": "0" * 64,
            "status": "approved",
        },
    ) as response:
        events = parse_sse(response.iter_lines())
    assert any(name == "error" for name, _ in events)
    assert client.get(f"/api/runs/{run_id}/analysis").status_code == 404


def test_syntax_failure_gets_one_repair_proposal_then_stops(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, approval = request_plan(
        client, "Query revenue trend for 2025 from the PostgreSQL sales data source."
    )
    connector = client.app.state.connector_registry.get("sales_postgres")

    async def fail_with_syntax(request: QueryExecutionRequest) -> None:
        del request
        raise QueryExecutionFailure("syntax", "The read-only query has a syntax error.")

    monkeypatch.setattr(connector, "execute", fail_with_syntax)
    with client.stream(
        "POST",
        f"/api/runs/{run_id}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": approval["payload_hash"],
            "status": "approved",
        },
    ) as response:
        events = parse_sse(response.iter_lines())
    error = next(data for name, data in events if name == "error")
    assert "new approval" in str(error["message"])
    trace = client.get(f"/api/runs/{run_id}/trace").json()
    repair = next(item for item in trace if item["event_type"] == "query.repair.proposed")
    assert repair["safe_details"]["repair_attempts"] == 1
    assert len(repair["safe_details"]["repair_sql_hash"]) == 64
    assert client.get(f"/api/runs/{run_id}/analysis").status_code == 404


@pytest.mark.asyncio
async def test_connector_remains_read_only_even_if_gateway_is_bypassed(tmp_path: Path) -> None:
    manager = DemoDatabaseManager(tmp_path)
    await manager.initialize()
    config = demo_source_configs()[0]
    connector = DemoReadOnlyConnector(config, manager.path_for(config.id))
    with pytest.raises(QueryExecutionFailure):
        await connector.execute(
            QueryExecutionRequest(
                source_id=config.id,
                sql="DELETE FROM daily_sales",
                parameters={},
                timeout_seconds=5,
                max_rows=10,
                max_result_bytes=1_000,
            )
        )


@pytest.mark.parametrize("chart_type", list(ChartKind))
def test_all_plotly_chart_types_validate(chart_type: ChartKind) -> None:
    rows = [
        {
            "period": "2025-01-01",
            "value": 10.0,
            "segment": "A",
            "spend": 5.0,
            "revenue": 10.0,
            "channel": "Search",
        },
        {
            "period": "2025-02-01",
            "value": 12.0,
            "segment": "B",
            "spend": 7.0,
            "revenue": 12.0,
            "channel": "Social",
        },
    ]
    dataset = Dataset(
        id="dataset",
        source_ids=["sales_postgres"],
        query_proposal_ids=["query"],
        columns=list(rows[0]),
        rows=rows,
        row_count=2,
        result_bytes=100,
        quality=DatasetQuality(
            row_count=2,
            missing_by_column={column: 0 for column in rows[0]},
            duplicate_rows=0,
        ),
    )
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.TREND,
        metric="revenue",
        dimensions=["period"],
        source_ids=["sales_postgres"],
        chart_type=chart_type,
        success_criteria="render",
    )
    computation = AnalysisComputation(
        summary={"last": 12.0, "rate": 0.12},
        conclusions=[
            Conclusion(text="Test", epistemic_label="Confirmed", evidence_ids=["evidence"])
        ],
        evidence=[],
    )
    spec = ChartBuilder(PlotlySpecValidator()).build(intent, dataset, computation)
    assert spec.chart_type == chart_type
    PlotlySpecValidator().validate(spec.figure)


def test_line_chart_splits_requested_category_series() -> None:
    rows = [
        {"period": "2026-07-15", "channel": "web", "value": 0.1, "visitors": 10, "conversions": 1},
        {"period": "2026-07-16", "channel": "web", "value": 0.2, "visitors": 10, "conversions": 2},
        {"period": "2026-07-15", "channel": "app", "value": 0.3, "visitors": 10, "conversions": 3},
        {"period": "2026-07-16", "channel": "app", "value": 0.4, "visitors": 10, "conversions": 4},
    ]
    dataset = Dataset(
        id="daily-rate",
        source_ids=["super_agent_uat"],
        query_proposal_ids=["query"],
        columns=list(rows[0]),
        rows=rows,
        row_count=len(rows),
        result_bytes=200,
        quality=DatasetQuality(
            row_count=len(rows),
            missing_by_column={column: 0 for column in rows[0]},
            duplicate_rows=0,
        ),
    )
    intent = AnalysisIntent(
        analysis_type=AnalysisKind.TREND,
        metric="WHTR",
        dimensions=["period", "channel"],
        source_ids=["super_agent_uat"],
        chart_type=ChartKind.LINE,
        success_criteria="render daily series",
    )
    computation = AnalysisComputation(summary={}, conclusions=[], evidence=[])

    spec = ChartBuilder(PlotlySpecValidator()).build(intent, dataset, computation)

    assert [trace["name"] for trace in spec.figure["data"]] == ["app", "web"]
    assert spec.figure["layout"]["yaxis"]["tickformat"] == ".1%"


def test_gateway_allows_aggregate_only_column_without_raw_exposure() -> None:
    base = demo_source_configs()[0]
    source = base.model_copy(
        update={"denied_columns": set(), "aggregate_only_columns": {"customer_email"}}
    )
    accepted = QueryProposal(
        id="aggregate-only",
        source_id=source.id,
        sql=(
            "SELECT SUM(CASE WHEN customer_email IS NOT NULL THEN 1 ELSE 0 END) AS value "
            "FROM daily_sales"
        ),
        parameters={},
        purpose="aggregate protected field",
        max_rows=100,
        max_result_bytes=10_000,
        timeout_seconds=5,
    )
    SQLSafetyGateway().validate(accepted, source)
    rejected = accepted.model_copy(
        update={"id": "raw-protected", "sql": "SELECT customer_email FROM daily_sales"}
    )
    with pytest.raises(SQLPolicyViolation) as caught:
        SQLSafetyGateway().validate(rejected, source)
    assert caught.value.code == "column_aggregate_only"


def test_request_changes_requires_comment_and_records_only_comment_hash(
    client: TestClient,
) -> None:
    run_id, approval = request_plan(
        client, "Query revenue trend for 2025 from the PostgreSQL sales data source."
    )
    with client.stream(
        "POST",
        f"/api/runs/{run_id}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": approval["payload_hash"],
            "status": "changes_requested",
        },
    ) as response:
        missing_events = parse_sse(response.iter_lines())
    assert any(name == "error" for name, _ in missing_events)

    run_id, approval = request_plan(
        client, "Query revenue trend for 2025 from the PostgreSQL sales data source."
    )
    comment = "Group by month and use net revenue."
    with client.stream(
        "POST",
        f"/api/runs/{run_id}/approval/stream",
        json={
            "approval_id": approval["approval_id"],
            "payload_hash": approval["payload_hash"],
            "status": "changes_requested",
            "comment": comment,
        },
    ) as response:
        events = parse_sse(response.iter_lines())
    decision = next(data for name, data in events if name == "approval.decision")
    assert decision["decision"] == "changes_requested"
    trace = client.get(f"/api/runs/{run_id}/trace").json()
    decided = next(item for item in trace if item["event_type"] == "analysis.approval.decided")
    assert len(decided["safe_details"]["comment_hash"]) == 64
    assert comment not in str(decided)
