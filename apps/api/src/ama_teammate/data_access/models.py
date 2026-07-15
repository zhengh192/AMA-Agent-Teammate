from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DatabaseDialect(StrEnum):
    POSTGRESQL = "postgres"
    MYSQL = "mysql"
    SQL_SERVER = "tsql"


class ColumnCatalog(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    description: str = ""


class TableCatalog(BaseModel):
    name: str
    columns: list[ColumnCatalog]
    description: str = ""

    @property
    def column_names(self) -> set[str]:
        return {column.name.lower() for column in self.columns}


class DataSourceConfig(BaseModel):
    id: str
    display_name: str
    dialect: DatabaseDialect
    secret_ref: str
    read_only: bool = True
    allowed_schemas: set[str] = Field(default_factory=lambda: {"main"})
    tables: dict[str, TableCatalog]
    denied_columns: set[str] = Field(default_factory=set)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_rows: int = Field(default=1_000, gt=0, le=100_000)
    max_result_bytes: int = Field(default=1_048_576, gt=0)

    def redacted(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "dialect": self.dialect.value,
            "read_only": self.read_only,
            "allowed_schemas": sorted(self.allowed_schemas),
            "allowed_tables": sorted(self.tables),
            "denied_columns": sorted(self.denied_columns),
            "timeout_seconds": self.timeout_seconds,
            "max_rows": self.max_rows,
            "max_result_bytes": self.max_result_bytes,
            "secret_ref": "[REDACTED]",
        }


class ConnectorHealth(BaseModel):
    source_id: str
    ok: bool
    safe_message: str
    latency_ms: float


class QueryExecutionRequest(BaseModel):
    source_id: str
    sql: str
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    timeout_seconds: float
    max_rows: int
    max_result_bytes: int


class QueryExecutionResult(BaseModel):
    source_id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    result_bytes: int
    duration_ms: float


class QueryExecutionFailure(RuntimeError):
    def __init__(self, category: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message
