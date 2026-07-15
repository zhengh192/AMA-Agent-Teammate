from __future__ import annotations

from typing import Protocol

from ama_teammate.data_access.models import (
    ConnectorHealth,
    DataSourceConfig,
    QueryExecutionRequest,
    QueryExecutionResult,
)


class ReadOnlyConnector(Protocol):
    config: DataSourceConfig

    async def health_check(self) -> ConnectorHealth: ...

    async def execute(self, request: QueryExecutionRequest) -> QueryExecutionResult: ...

    async def close(self) -> None: ...
