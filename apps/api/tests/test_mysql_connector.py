from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ama_teammate.config import Settings
from ama_teammate.data_access.models import QueryExecutionFailure, QueryExecutionRequest
from ama_teammate.data_access.mysql import (
    MySQLCatalogSnapshot,
    MySQLColumnSnapshot,
    MySQLConnectionOptions,
    MySQLPrivilegeAssessment,
    MySQLReadOnlyConnector,
    MySQLTableSnapshot,
    _bounded_result_rows,
    _pymysql_parameter_sql,
    assess_mysql_grants,
    validate_mysql_select,
)


def options(*, query_enabled: bool = False) -> MySQLConnectionOptions:
    return MySQLConnectionOptions(
        host="uat.example.internal",
        port=443,
        username="read_only",
        password="do-not-log",
        database="sa_logs",
        allowed_tables=frozenset({"visit_log", "turn_log", "telemetry_log"}),
        query_enabled=query_enabled,
    )


def snapshot() -> MySQLCatalogSnapshot:
    return MySQLCatalogSnapshot(
        source_id="super_agent_uat",
        database="sa_logs",
        captured_at=datetime.now(UTC),
        tls_cipher="TLS_AES_256_GCM_SHA384",
        privilege_assessment=MySQLPrivilegeAssessment(
            read_only=True,
            privileges=["SELECT", "USAGE"],
        ),
        tables=[
            MySQLTableSnapshot(
                name="turn_log",
                table_type="BASE TABLE",
                engine="InnoDB",
                estimated_rows=10,
                columns=[
                    MySQLColumnSnapshot(
                        name="turn_id",
                        data_type="varchar(64)",
                        nullable=False,
                        ordinal_position=1,
                        default_present=False,
                    ),
                    MySQLColumnSnapshot(
                        name="user_input",
                        data_type="text",
                        nullable=True,
                        ordinal_position=2,
                        default_present=False,
                    ),
                ],
                indexes=[],
            )
        ],
        missing_allowlisted_tables=["telemetry_log", "visit_log"],
    )


def test_production_rejects_uat_detail_field_switch() -> None:
    settings = Settings(
        _env_file=None,
        ama_env="production",
        ama_super_agent_uat_query_enabled=True,
        ama_super_agent_uat_host="uat.example.internal",
        ama_super_agent_uat_username="read_only",
        ama_super_agent_uat_password="secret",
        ama_super_agent_uat_allow_detail_fields=True,
    )
    assert (
        "AMA_SUPER_AGENT_UAT_ALLOW_DETAIL_FIELDS is development-only"
        in settings.super_agent_uat_runtime_validation_errors()
    )


def test_options_redaction_never_exposes_credentials_or_host() -> None:
    redacted = options().redacted()
    rendered = str(redacted)
    assert "do-not-log" not in rendered
    assert "read_only" not in rendered
    assert "uat.example.internal" not in rendered
    assert redacted["password"] == "[REDACTED]"


def test_grant_assessment_accepts_select_and_rejects_write_privileges() -> None:
    accepted = assess_mysql_grants(
        [
            "GRANT USAGE ON *.* TO `read_only`@`%`",
            "GRANT SELECT, SHOW VIEW ON `sa_logs`.* TO `read_only`@`%`",
        ],
        "sa_logs",
    )
    assert accepted.read_only is True
    assert accepted.denied_reasons == []

    rejected = assess_mysql_grants(
        ["GRANT SELECT, INSERT, UPDATE ON `sa_logs`.* TO `unsafe`@`%`"],
        "sa_logs",
    )
    assert rejected.read_only is False
    assert "INSERT" in rejected.denied_reasons[0]
    assert "UPDATE" in rejected.denied_reasons[0]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT session_id FROM visit_log LIMIT 10",
        ("WITH recent AS (SELECT session_id FROM sa_logs.visit_log) SELECT session_id FROM recent"),
    ],
)
def test_mysql_sql_guard_accepts_allowlisted_selects(sql: str) -> None:
    validate_mysql_select(
        sql,
        database="sa_logs",
        allowed_tables=frozenset({"visit_log", "turn_log", "telemetry_log"}),
    )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE visit_log SET session_id = 'x'",
        "SELECT * FROM mysql.user",
        "SELECT * FROM unapproved_table",
        "SELECT * FROM visit_log; SELECT * FROM turn_log",
    ],
)
def test_mysql_sql_guard_rejects_writes_scope_escape_and_multiple_statements(
    sql: str,
) -> None:
    with pytest.raises(QueryExecutionFailure) as exc_info:
        validate_mysql_select(
            sql,
            database="sa_logs",
            allowed_tables=frozenset({"visit_log", "turn_log", "telemetry_log"}),
        )
    assert exc_info.value.category == "policy"


@pytest.mark.asyncio
async def test_connector_refuses_business_rows_until_review() -> None:
    catalog = snapshot()
    connector = MySQLReadOnlyConnector(
        options(),
        catalog.to_source_config(
            secret_ref="env:super_agent_uat",
            timeout_seconds=15,
            max_rows=1_000,
            max_result_bytes=1_048_576,
        ),
    )
    with pytest.raises(QueryExecutionFailure) as exc_info:
        await connector.execute(
            QueryExecutionRequest(
                source_id="super_agent_uat",
                sql="SELECT session_id FROM visit_log",
                timeout_seconds=5,
                max_rows=10,
                max_result_bytes=10_000,
            )
        )
    assert exc_info.value.category == "policy"
    assert "disabled" in exc_info.value.safe_message.lower()


def test_discovered_config_denies_likely_sensitive_payload_columns() -> None:
    config = snapshot().to_source_config(
        secret_ref="env:super_agent_uat",
        timeout_seconds=15,
        max_rows=1_000,
        max_result_bytes=1_048_576,
    )
    assert "user_input" in config.denied_columns
    assert config.redacted()["secret_ref"] == "[REDACTED]"


def test_discovered_config_allows_encrypted_detail_fields_when_explicitly_enabled() -> None:
    config = snapshot().to_source_config(
        secret_ref="env:super_agent_uat",
        timeout_seconds=15,
        max_rows=1_000,
        max_result_bytes=1_048_576,
        allow_detail_fields=True,
    )
    assert config.denied_columns == set()
    assert config.aggregate_only_columns == set()
    validate_mysql_select(
        "SELECT turn_id, user_input FROM turn_log LIMIT 10",
        database="sa_logs",
        allowed_tables=frozenset({"turn_log"}),
        denied_columns=frozenset(config.denied_columns),
        aggregate_only_columns=frozenset(config.aggregate_only_columns),
    )


def test_mysql_parameter_adapter_uses_driver_named_parameters() -> None:
    sql = "SELECT session_id FROM visit_log WHERE start_time >= :start_date"
    assert _pymysql_parameter_sql(sql, {"start_date": "2026-06-01"}) == (
        "SELECT session_id FROM visit_log WHERE start_time >= %(start_date)s"
    )


def test_mysql_sql_guard_rejects_discovered_sensitive_columns() -> None:
    with pytest.raises(QueryExecutionFailure) as exc_info:
        validate_mysql_select(
            "SELECT user_input FROM turn_log",
            database="sa_logs",
            allowed_tables=frozenset({"turn_log"}),
            denied_columns=frozenset({"user_input"}),
        )
    assert exc_info.value.category == "policy"


def test_mysql_guard_allows_protected_identifier_only_inside_aggregate() -> None:
    aggregate_sql = (
        "SELECT SUM(CASE WHEN eticket_case_number IS NOT NULL THEN 1 ELSE 0 END) AS value "
        "FROM visit_log"
    )
    validate_mysql_select(
        aggregate_sql,
        database="sa_logs",
        allowed_tables=frozenset({"visit_log"}),
        aggregate_only_columns=frozenset({"eticket_case_number"}),
    )
    with pytest.raises(QueryExecutionFailure):
        validate_mysql_select(
            "SELECT eticket_case_number FROM visit_log",
            database="sa_logs",
            allowed_tables=frozenset({"visit_log"}),
            aggregate_only_columns=frozenset({"eticket_case_number"}),
        )

def test_result_rows_are_truncated_instead_of_failing_the_run() -> None:
    rows = [
        {"session_id": "s1", "bot_response": "a" * 2_000},
        {"session_id": "s2", "bot_response": "b" * 2_000},
    ]

    bounded, truncated = _bounded_result_rows(rows, 700)

    assert truncated is True
    assert bounded
    assert "[truncated]" in str(bounded[0]["bot_response"])
    assert len(
        __import__("json").dumps(
            bounded, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ) <= 700
