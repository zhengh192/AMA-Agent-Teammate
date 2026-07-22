from __future__ import annotations

import asyncio
import json
import re
import ssl
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymysql  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pymysql.cursors import DictCursor  # type: ignore[import-untyped]
from sqlglot import exp, parse

from ama_teammate.data_access.models import (
    ColumnCatalog,
    ConnectorHealth,
    DatabaseDialect,
    DataSourceConfig,
    QueryExecutionFailure,
    QueryExecutionRequest,
    QueryExecutionResult,
    TableCatalog,
)
from ama_teammate.sql_policy.aggregate_only import aggregate_only_violations

_READ_ONLY_PRIVILEGES = frozenset({"SELECT", "SHOW VIEW", "USAGE"})
_SENSITIVE_EXACT_NAMES = frozenset(
    {
        "bot_thinking",
        "chat_log",
        "chat_log_text",
        "chat_summary",
        "customer_information",
        "eticket_case_number",
        "event_data",
        "lenovo_id",
        "msd_case_number",
        "msd_customer_info",
        "msd_shipping_info",
        "msd_wo_number",
        "msd_wo_sn",
        "serial_number",
        "source_url",
        "survey_comments",
        "user_id",
        "user_info",
        "user_input",
    }
)
_SENSITIVE_NAME_PARTS = frozenset(
    {
        "address",
        "content",
        "email",
        "input",
        "message",
        "output",
        "payload",
        "phone",
        "chat",
        "comment",
        "customer",
        "info",
        "summary",
        "thinking",
        "url",
        "prompt",
        "response",
        "serial",
        "shipping",
        "transcript",
    }
)
_AGGREGATE_ONLY_EXACT_NAMES = frozenset({"eticket_case_number", "serial_number"})
_GRANT_PATTERN = re.compile(r"^GRANT\s+(?P<privileges>.+?)\s+ON\s+(?P<scope>.+?)\s+TO\s+", re.I)


class MySQLConnectionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = "super_agent_uat"
    display_name: str = "Super Agent UAT"
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: SecretStr
    database: str = Field(min_length=1)
    allowed_tables: frozenset[str] = Field(min_length=1)
    ssl_ca_path: Path | None = None
    allow_insecure_transport: bool = False
    allow_detail_fields: bool = False
    connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    read_timeout_seconds: int = Field(default=15, ge=1, le=120)
    write_timeout_seconds: int = Field(default=10, ge=1, le=60)
    max_rows: int = Field(default=1_000, ge=1, le=10_000)
    max_result_bytes: int = Field(default=1_048_576, ge=1)
    query_enabled: bool = False

    def redacted(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "host": "[REDACTED]",
            "port": self.port,
            "username": "[REDACTED]",
            "password": "[REDACTED]",
            "database": self.database,
            "allowed_tables": sorted(self.allowed_tables),
            "tls_required": not self.allow_insecure_transport,
            "transport_security": "plaintext-development-exception"
            if self.allow_insecure_transport
            else "tls-verified",
            "query_enabled": self.query_enabled,
        }


class MySQLPrivilegeAssessment(BaseModel):
    read_only: bool
    privileges: list[str]
    scope_warnings: list[str] = Field(default_factory=list)
    denied_reasons: list[str] = Field(default_factory=list)


class MySQLIndexSnapshot(BaseModel):
    name: str
    unique: bool
    columns: list[str]


class MySQLColumnSnapshot(BaseModel):
    name: str
    data_type: str
    nullable: bool
    ordinal_position: int
    default_present: bool
    extra: str = ""
    comment: str = ""


class MySQLTableSnapshot(BaseModel):
    name: str
    table_type: str
    engine: str | None = None
    estimated_rows: int | None = None
    columns: list[MySQLColumnSnapshot]
    indexes: list[MySQLIndexSnapshot]


class MySQLCatalogSnapshot(BaseModel):
    source_id: str
    database: str
    captured_at: datetime
    tls_cipher: str
    privilege_assessment: MySQLPrivilegeAssessment
    tables: list[MySQLTableSnapshot]
    missing_allowlisted_tables: list[str]

    def to_source_config(
        self,
        *,
        secret_ref: str,
        timeout_seconds: float,
        max_rows: int,
        max_result_bytes: int,
        allow_detail_fields: bool = False,
    ) -> DataSourceConfig:
        aggregate_only_columns = (
            set()
            if allow_detail_fields
            else {
                column.name
                for table in self.tables
                for column in table.columns
                if column.name.lower() in _AGGREGATE_ONLY_EXACT_NAMES
            }
        )
        denied_columns = (
            set()
            if allow_detail_fields
            else {
                column.name
                for table in self.tables
                for column in table.columns
                if column.name not in aggregate_only_columns
                and (
                    column.name.lower() in _SENSITIVE_EXACT_NAMES
                    or any(part in column.name.lower() for part in _SENSITIVE_NAME_PARTS)
                )
            }
        )
        return DataSourceConfig(
            id=self.source_id,
            display_name="Super Agent UAT",
            dialect=DatabaseDialect.MYSQL,
            execution_dialect="mysql",
            secret_ref=secret_ref,
            read_only=True,
            allowed_schemas={self.database},
            tables={
                table.name: TableCatalog(
                    name=table.name,
                    columns=[
                        ColumnCatalog(
                            name=column.name,
                            data_type=column.data_type,
                            nullable=column.nullable,
                            description=column.comment,
                        )
                        for column in table.columns
                    ],
                    description=f"{table.table_type}; engine={table.engine or 'unknown'}",
                )
                for table in self.tables
            },
            denied_columns=denied_columns,
            aggregate_only_columns=aggregate_only_columns,
            timeout_seconds=timeout_seconds,
            max_rows=max_rows,
            max_result_bytes=max_result_bytes,
        )


class MySQLCatalogError(RuntimeError):
    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message


def assess_mysql_grants(grants: list[str], database: str) -> MySQLPrivilegeAssessment:
    privileges: set[str] = set()
    denied_reasons: list[str] = []
    scope_warnings: list[str] = []
    normalized_database = f"`{database.lower()}`"
    for grant in grants:
        match = _GRANT_PATTERN.match(grant.strip())
        if match is None:
            if grant.upper().startswith("GRANT PROXY"):
                denied_reasons.append("The account has PROXY privilege.")
            continue
        current = {
            item.strip().upper() for item in match.group("privileges").split(",") if item.strip()
        }
        privileges.update(current)
        unsafe = sorted(current - _READ_ONLY_PRIVILEGES)
        if unsafe:
            denied_reasons.append(
                "The account has non-read-only privileges: " + ", ".join(unsafe) + "."
            )
        scope = match.group("scope").lower()
        if "select" in {item.lower() for item in current} and normalized_database not in scope:
            scope_warnings.append("SELECT is granted outside the requested database scope.")
    return MySQLPrivilegeAssessment(
        read_only=not denied_reasons,
        privileges=sorted(privileges),
        scope_warnings=sorted(set(scope_warnings)),
        denied_reasons=sorted(set(denied_reasons)),
    )


class MySQLReadOnlyConnector:
    def __init__(self, options: MySQLConnectionOptions, config: DataSourceConfig) -> None:
        self.options = options
        self.config = config

    @classmethod
    async def discover(
        cls, options: MySQLConnectionOptions
    ) -> tuple[MySQLReadOnlyConnector, MySQLCatalogSnapshot]:
        snapshot = await asyncio.to_thread(_read_catalog_sync, options)
        config = snapshot.to_source_config(
            secret_ref=f"env:{options.source_id}",
            timeout_seconds=float(options.read_timeout_seconds),
            max_rows=options.max_rows,
            max_result_bytes=options.max_result_bytes,
            allow_detail_fields=options.allow_detail_fields,
        )
        return cls(options, config), snapshot

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            snapshot = await asyncio.to_thread(_read_catalog_sync, self.options)
            ok = (
                snapshot.privilege_assessment.read_only
                and (bool(snapshot.tls_cipher) or self.options.allow_insecure_transport)
                and not snapshot.missing_allowlisted_tables
            )
            if ok and snapshot.tls_cipher:
                message = "TLS-verified read-only MySQL catalog is available."
            elif ok:
                message = "Read-only UAT catalog is available through an explicit development plaintext exception."
            else:
                message = "MySQL catalog failed a read-only, transport, or allowlist check."
        except Exception:
            ok = False
            message = "MySQL catalog is unavailable."
        return ConnectorHealth(
            source_id=self.config.id,
            ok=ok,
            safe_message=message,
            latency_ms=(time.perf_counter() - started) * 1_000,
        )

    async def execute(self, request: QueryExecutionRequest) -> QueryExecutionResult:
        if not self.options.query_enabled:
            raise QueryExecutionFailure(
                "policy",
                "UAT business-row queries are disabled until metadata and sensitivity review.",
            )
        if request.source_id != self.config.id:
            raise QueryExecutionFailure("policy", "Query source does not match connector.")
        validate_mysql_select(
            request.sql,
            database=self.options.database,
            allowed_tables=self.options.allowed_tables,
            denied_columns=frozenset(self.config.denied_columns),
            aggregate_only_columns=frozenset(self.config.aggregate_only_columns),
        )
        started = time.perf_counter()
        try:
            async with asyncio.timeout(
                min(request.timeout_seconds, self.config.timeout_seconds) + 1
            ):
                columns, rows, row_truncated = await asyncio.to_thread(
                    self._execute_sync, request
                )
        except TimeoutError as exc:
            raise QueryExecutionFailure("timeout", "The read-only query timed out.") from exc
        except QueryExecutionFailure:
            raise
        except pymysql.err.ProgrammingError as exc:
            raise QueryExecutionFailure("syntax", "The read-only query failed safely.") from exc
        except pymysql.MySQLError as exc:
            raise QueryExecutionFailure("database", "The read-only query failed safely.") from exc

        byte_limit = min(request.max_result_bytes, self.config.max_result_bytes)
        rows, byte_truncated = _bounded_result_rows(rows, byte_limit)
        result_bytes = len(
            json.dumps(rows, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        )
        truncation_reason = (
            "byte_limit" if byte_truncated else ("row_limit" if row_truncated else None)
        )
        return QueryExecutionResult(
            source_id=self.config.id,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            result_bytes=result_bytes,
            duration_ms=(time.perf_counter() - started) * 1_000,
            truncated=row_truncated or byte_truncated,
            truncation_reason=truncation_reason,
        )

    def _execute_sync(
        self, request: QueryExecutionRequest
    ) -> tuple[list[str], list[dict[str, Any]], bool]:
        limit = min(request.max_rows, self.config.max_rows)
        connection = _connect(self.options)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    _pymysql_parameter_sql(request.sql, request.parameters),
                    request.parameters,
                )
                raw_rows = list(cursor.fetchmany(limit + 1))
                columns = [item[0] for item in cursor.description or ()]
        finally:
            connection.close()
        truncated = len(raw_rows) > limit
        return columns, [dict(row) for row in raw_rows[:limit]], truncated

    async def close(self) -> None:
        return None


def _bounded_result_rows(
    rows: list[dict[str, Any]], max_bytes: int
) -> tuple[list[dict[str, Any]], bool]:
    bounded: list[dict[str, Any]] = []
    encoded_bytes = 2
    truncated = False
    for source_row in rows:
        row = dict(source_row)
        encoded = json.dumps(
            row, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) + 2 > max_bytes:
            strings = [key for key, value in row.items() if isinstance(value, str)]
            if strings:
                per_field = max(128, max_bytes // max(4, len(strings) * 2))
                for key in strings:
                    value = str(row[key])
                    if len(value) > per_field:
                        row[key] = value[:per_field] + "… [truncated]"
                encoded = json.dumps(
                    row, ensure_ascii=False, default=str, separators=(",", ":")
                ).encode("utf-8")
                truncated = True
        separator = 1 if bounded else 0
        if encoded_bytes + separator + len(encoded) > max_bytes:
            truncated = True
            break
        bounded.append(row)
        encoded_bytes += separator + len(encoded)
    return bounded, truncated or len(bounded) < len(rows)


def _ssl_context(options: MySQLConnectionOptions) -> ssl.SSLContext:
    context = ssl.create_default_context(
        cafile=str(options.ssl_ca_path) if options.ssl_ca_path else None
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _connect(options: MySQLConnectionOptions) -> Any:
    return pymysql.connect(
        host=options.host,
        port=options.port,
        user=options.username,
        password=options.password.get_secret_value(),
        database=options.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        local_infile=False,
        connect_timeout=options.connect_timeout_seconds,
        read_timeout=options.read_timeout_seconds,
        write_timeout=options.write_timeout_seconds,
        ssl=None if options.allow_insecure_transport else _ssl_context(options),
    )


def validate_mysql_select(
    sql: str,
    *,
    database: str,
    allowed_tables: frozenset[str],
    denied_columns: frozenset[str] = frozenset(),
    aggregate_only_columns: frozenset[str] = frozenset(),
) -> None:
    try:
        statements = parse(sql, read="mysql")
    except Exception as exc:
        raise QueryExecutionFailure("policy", "SQL could not be parsed safely.") from exc
    if len(statements) != 1:
        raise QueryExecutionFailure("policy", "Exactly one read-only statement is allowed.")
    statement = statements[0]
    if statement is None:
        raise QueryExecutionFailure("policy", "SQL could not be parsed safely.")
    forbidden = (
        exp.Alter,
        exp.Command,
        exp.Create,
        exp.Delete,
        exp.Drop,
        exp.Insert,
        exp.Merge,
        exp.Transaction,
        exp.Update,
    )
    if any(statement.find(node) is not None for node in forbidden):
        raise QueryExecutionFailure("policy", "Only SELECT and read-only CTE queries are allowed.")
    if statement.find(exp.Select) is None:
        raise QueryExecutionFailure("policy", "Only SELECT and read-only CTE queries are allowed.")
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in cte_names:
            continue
        schema = table.db.lower() if table.db else database.lower()
        if schema != database.lower() or table_name not in allowed_tables:
            raise QueryExecutionFailure(
                "policy", "The query references a table outside the approved allowlist."
            )
    referenced_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
    if referenced_columns & {column.lower() for column in denied_columns}:
        raise QueryExecutionFailure("policy", "The query references a denied column.")
    if aggregate_only_violations(statement, aggregate_only_columns):
        raise QueryExecutionFailure(
            "policy",
            "The query references a protected column outside an aggregate expression.",
        )


def _pymysql_parameter_sql(sql: str, parameters: Mapping[str, object]) -> str:
    for name in sorted(parameters, key=len, reverse=True):
        sql = re.sub(rf":{re.escape(name)}\b", f"%({name})s", sql)
    return sql


def _safe_operational_error(exc: BaseException) -> str:
    code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    detail = str(exc.args[1] if len(exc.args) > 1 else "").lower()
    if code == 2026 and "server doesn't support" in detail:
        return (
            "The endpoint responded as MySQL but did not advertise TLS. "
            "Insecure fallback is prohibited."
        )
    if code == 1045:
        return "MySQL rejected the supplied identity or its database access."
    if code == 2003:
        return "The MySQL endpoint is unreachable from this environment."
    if code == 2026:
        return "MySQL TLS verification failed. Check the approved CA and endpoint identity."
    return (
        "Unable to establish a TLS-verified MySQL connection. "
        "Check endpoint, protocol, CA, and credentials."
    )


def _read_catalog_sync(options: MySQLConnectionOptions) -> MySQLCatalogSnapshot:
    try:
        connection = _connect(options)
        try:
            with connection.cursor() as cursor:
                tls_cipher = (
                    "" if options.allow_insecure_transport else _read_tls_cipher(cursor)
                )
                if not tls_cipher and not options.allow_insecure_transport:
                    raise MySQLCatalogError("The MySQL session did not negotiate TLS.")
                assessment = assess_mysql_grants(_read_grants(cursor), options.database)
                if not assessment.read_only:
                    raise MySQLCatalogError(
                        "The supplied account has non-read-only privileges; catalog access stopped."
                    )
                tables = _read_tables(cursor, options.database, options.allowed_tables)
        finally:
            connection.close()
    except MySQLCatalogError:
        raise
    except pymysql.err.OperationalError as exc:
        raise MySQLCatalogError(_safe_operational_error(exc)) from exc
    except pymysql.MySQLError as exc:
        raise MySQLCatalogError("MySQL catalog discovery failed safely.") from exc
    discovered = {table.name for table in tables}
    return MySQLCatalogSnapshot(
        source_id=options.source_id,
        database=options.database,
        captured_at=datetime.now(UTC),
        tls_cipher=tls_cipher,
        privilege_assessment=assessment,
        tables=tables,
        missing_allowlisted_tables=sorted(options.allowed_tables - discovered),
    )


def _read_tls_cipher(cursor: Any) -> str:
    cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
    row = cursor.fetchone()
    return str(row.get("Value") or "") if row else ""


def _read_grants(cursor: Any) -> list[str]:
    cursor.execute("SHOW GRANTS")
    return [str(next(iter(row.values()))) for row in cursor.fetchall() if row]


def _read_tables(
    cursor: Any, database: str, allowed_tables: frozenset[str]
) -> list[MySQLTableSnapshot]:
    table_names = sorted(allowed_tables)
    placeholders = ", ".join(["%s"] * len(table_names))
    cursor.execute(
        "SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS "
        "FROM information_schema.TABLES "
        f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders}) "
        "ORDER BY TABLE_NAME",
        [database, *table_names],
    )
    table_rows = list(cursor.fetchall())
    cursor.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, ORDINAL_POSITION, "
        "COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT "
        "FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders}) "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION",
        [database, *table_names],
    )
    columns_by_table: dict[str, list[MySQLColumnSnapshot]] = {name: [] for name in table_names}
    for row in cursor.fetchall():
        columns_by_table[str(row["TABLE_NAME"])].append(
            MySQLColumnSnapshot(
                name=str(row["COLUMN_NAME"]),
                data_type=str(row["COLUMN_TYPE"]),
                nullable=str(row["IS_NULLABLE"]).upper() == "YES",
                ordinal_position=int(row["ORDINAL_POSITION"]),
                default_present=row["COLUMN_DEFAULT"] is not None,
                extra=str(row["EXTRA"] or ""),
                comment=str(row["COLUMN_COMMENT"] or ""),
            )
        )
    cursor.execute(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
        "FROM information_schema.STATISTICS "
        f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders}) "
        "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
        [database, *table_names],
    )
    index_parts: dict[tuple[str, str], list[tuple[int, str]]] = {}
    unique_by_index: dict[tuple[str, str], bool] = {}
    for row in cursor.fetchall():
        key = (str(row["TABLE_NAME"]), str(row["INDEX_NAME"]))
        index_parts.setdefault(key, []).append((int(row["SEQ_IN_INDEX"]), str(row["COLUMN_NAME"])))
        unique_by_index[key] = not bool(row["NON_UNIQUE"])
    indexes_by_table: dict[str, list[MySQLIndexSnapshot]] = {name: [] for name in table_names}
    for (table_name, index_name), parts in sorted(index_parts.items()):
        indexes_by_table[table_name].append(
            MySQLIndexSnapshot(
                name=index_name,
                unique=unique_by_index[(table_name, index_name)],
                columns=[column for _, column in sorted(parts)],
            )
        )
    return [
        MySQLTableSnapshot(
            name=str(row["TABLE_NAME"]),
            table_type=str(row["TABLE_TYPE"]),
            engine=str(row["ENGINE"]) if row["ENGINE"] is not None else None,
            estimated_rows=int(row["TABLE_ROWS"]) if row["TABLE_ROWS"] is not None else None,
            columns=columns_by_table[str(row["TABLE_NAME"])],
            indexes=indexes_by_table[str(row["TABLE_NAME"])],
        )
        for row in table_rows
    ]
