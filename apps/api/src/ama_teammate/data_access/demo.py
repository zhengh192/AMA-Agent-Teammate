from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

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


def _table(name: str, columns: list[tuple[str, str, bool]], description: str) -> TableCatalog:
    return TableCatalog(
        name=name,
        description=description,
        columns=[
            ColumnCatalog(name=column, data_type=data_type, nullable=nullable)
            for column, data_type, nullable in columns
        ],
    )


def demo_source_configs() -> list[DataSourceConfig]:
    return [
        DataSourceConfig(
            id="sales_postgres",
            display_name="Demo Sales (PostgreSQL dialect)",
            dialect=DatabaseDialect.POSTGRESQL,
            secret_ref="local-demo://sales",
            tables={
                "daily_sales": _table(
                    "daily_sales",
                    [
                        ("sale_date", "date", False),
                        ("campaign_id", "text", False),
                        ("revenue", "decimal", False),
                        ("orders", "integer", False),
                        ("customer_email", "text", True),
                    ],
                    "Bounded monthly sales facts for the Phase 2 demo.",
                ),
                "segment_sales": _table(
                    "segment_sales",
                    [
                        ("month", "date", False),
                        ("region", "text", False),
                        ("segment", "text", False),
                        ("revenue", "decimal", False),
                    ],
                    "Revenue components by month, region, and segment.",
                ),
            },
            denied_columns={"customer_email"},
        ),
        DataSourceConfig(
            id="marketing_mysql",
            display_name="Demo Marketing (MySQL dialect)",
            dialect=DatabaseDialect.MYSQL,
            secret_ref="local-demo://marketing",
            tables={
                "campaigns": _table(
                    "campaigns",
                    [
                        ("campaign_id", "text", False),
                        ("channel", "text", False),
                        ("spend", "decimal", False),
                        ("impressions", "integer", False),
                        ("owner_token", "text", True),
                    ],
                    "Campaign channel and spend dimensions.",
                )
            },
            denied_columns={"owner_token"},
        ),
        DataSourceConfig(
            id="operations_sqlserver",
            display_name="Demo Operations (SQL Server dialect)",
            dialect=DatabaseDialect.SQL_SERVER,
            secret_ref="local-demo://operations",
            tables={
                "funnel_events": _table(
                    "funnel_events",
                    [
                        ("event_id", "text", True),
                        ("period", "date", False),
                        ("stage", "text", False),
                        ("visitors", "integer", True),
                        ("conversions", "integer", True),
                        ("campaign_id", "text", True),
                        ("user_phone", "text", True),
                    ],
                    "Funnel aggregates with intentional null and duplicate quality issues.",
                )
            },
            denied_columns={"user_phone"},
        ),
    ]


class DemoDatabaseManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        await self._initialize_sales()
        await self._initialize_marketing()
        await self._initialize_operations()

    def path_for(self, source_id: str) -> Path:
        return self.root / f"{source_id}.db"

    async def _reset(
        self, source_id: str, statements: list[str], rows: list[tuple[str, list[tuple[Any, ...]]]]
    ) -> None:
        path = self.path_for(source_id)
        async with aiosqlite.connect(path) as connection:
            for statement in statements:
                await connection.execute(statement)
            for sql, values in rows:
                await connection.executemany(sql, values)
            await connection.commit()

    async def _initialize_sales(self) -> None:
        daily_rows: list[tuple[Any, ...]] = []
        for month in range(1, 13):
            for index, campaign in enumerate(("C1", "C2", "C3"), start=1):
                revenue = 8_000 + month * 650 + index * 900 + (1_800 if month >= 7 else 0)
                orders = 80 + month * 4 + index * 7
                daily_rows.append((f"2025-{month:02d}-01", campaign, revenue, orders, None))
        segment_rows = [
            ("2025-01-01", "North", "Enterprise", 14_000),
            ("2025-01-01", "North", "SMB", 9_000),
            ("2025-01-01", "South", "Enterprise", 11_000),
            ("2025-02-01", "North", "Enterprise", 16_500),
            ("2025-02-01", "North", "SMB", 8_500),
            ("2025-02-01", "South", "Enterprise", 13_500),
        ]
        await self._reset(
            "sales_postgres",
            [
                "DROP TABLE IF EXISTS daily_sales",
                "DROP TABLE IF EXISTS segment_sales",
                "CREATE TABLE daily_sales (sale_date TEXT NOT NULL, campaign_id TEXT NOT NULL, revenue REAL NOT NULL, orders INTEGER NOT NULL, customer_email TEXT)",
                "CREATE TABLE segment_sales (month TEXT NOT NULL, region TEXT NOT NULL, segment TEXT NOT NULL, revenue REAL NOT NULL)",
            ],
            [
                ("INSERT INTO daily_sales VALUES (?, ?, ?, ?, ?)", daily_rows),
                ("INSERT INTO segment_sales VALUES (?, ?, ?, ?)", segment_rows),
            ],
        )

    async def _initialize_marketing(self) -> None:
        await self._reset(
            "marketing_mysql",
            [
                "DROP TABLE IF EXISTS campaigns",
                "CREATE TABLE campaigns (campaign_id TEXT NOT NULL, channel TEXT NOT NULL, spend REAL NOT NULL, impressions INTEGER NOT NULL, owner_token TEXT)",
            ],
            [
                (
                    "INSERT INTO campaigns VALUES (?, ?, ?, ?, ?)",
                    [
                        ("C1", "Search", 12_000, 420_000, None),
                        ("C2", "Social", 9_500, 510_000, None),
                        ("C3", "Partner", 7_000, 180_000, None),
                        ("C4", "Unmatched", 2_000, 50_000, None),
                    ],
                )
            ],
        )

    async def _initialize_operations(self) -> None:
        await self._reset(
            "operations_sqlserver",
            [
                "DROP TABLE IF EXISTS funnel_events",
                "CREATE TABLE funnel_events (event_id TEXT, period TEXT NOT NULL, stage TEXT NOT NULL, visitors INTEGER, conversions INTEGER, campaign_id TEXT, user_phone TEXT)",
            ],
            [
                (
                    "INSERT INTO funnel_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("E1", "2025-01-01", "landing", 1_000, 120, "C1", None),
                        ("E2", "2025-02-01", "landing", 1_200, 138, "C2", None),
                        ("E2", "2025-02-01", "landing", 1_200, 138, "C2", None),
                        (None, "2025-03-01", "landing", 900, None, "C3", None),
                    ],
                )
            ],
        )


class DemoReadOnlyConnector:
    def __init__(self, config: DataSourceConfig, database_path: Path) -> None:
        self.config = config
        self.database_path = database_path

    async def _connect(self) -> aiosqlite.Connection:
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = await aiosqlite.connect(uri, uri=True)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA query_only=ON")
        return connection

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            connection = await self._connect()
            try:
                await connection.execute("SELECT 1")
            finally:
                await connection.close()
            return ConnectorHealth(
                source_id=self.config.id,
                ok=True,
                safe_message="Read-only demo source is available.",
                latency_ms=(time.perf_counter() - started) * 1_000,
            )
        except Exception:
            return ConnectorHealth(
                source_id=self.config.id,
                ok=False,
                safe_message="Read-only demo source is unavailable.",
                latency_ms=(time.perf_counter() - started) * 1_000,
            )

    async def execute(self, request: QueryExecutionRequest) -> QueryExecutionResult:
        if request.source_id != self.config.id:
            raise QueryExecutionFailure("policy", "Query source does not match connector.")
        started = time.perf_counter()
        try:
            async with asyncio.timeout(min(request.timeout_seconds, self.config.timeout_seconds)):
                connection = await self._connect()
                try:
                    cursor = await connection.execute(request.sql, request.parameters)
                    columns = [description[0] for description in cursor.description or []]
                    raw_rows = list(
                        await cursor.fetchmany(min(request.max_rows, self.config.max_rows) + 1)
                    )
                finally:
                    await connection.close()
        except TimeoutError as exc:
            raise QueryExecutionFailure("timeout", "The read-only query timed out.") from exc
        except aiosqlite.Error as exc:
            category = "syntax" if "syntax" in str(exc).lower() else "database"
            raise QueryExecutionFailure(category, "The read-only query failed safely.") from exc

        if len(raw_rows) > min(request.max_rows, self.config.max_rows):
            raise QueryExecutionFailure("limit", "The query exceeded the approved row limit.")
        rows = [dict(row) for row in raw_rows]
        result_bytes = len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"))
        if result_bytes > min(request.max_result_bytes, self.config.max_result_bytes):
            raise QueryExecutionFailure("limit", "The query exceeded the approved byte limit.")
        return QueryExecutionResult(
            source_id=self.config.id,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            result_bytes=result_bytes,
            duration_ms=(time.perf_counter() - started) * 1_000,
        )

    async def close(self) -> None:
        return None
