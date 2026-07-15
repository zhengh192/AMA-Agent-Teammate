from __future__ import annotations

import asyncio
from collections.abc import Sequence

from ama_teammate.data_access.base import ReadOnlyConnector
from ama_teammate.data_access.models import ConnectorHealth, DataSourceConfig


class ConnectorRegistry:
    def __init__(self, connectors: Sequence[ReadOnlyConnector]) -> None:
        self._connectors = {connector.config.id: connector for connector in connectors}
        if len(self._connectors) != len(connectors):
            raise ValueError("Duplicate data source id")
        if any(not connector.config.read_only for connector in connectors):
            raise ValueError("Phase 2 registry accepts read-only connectors only")

    def get(self, source_id: str) -> ReadOnlyConnector:
        try:
            return self._connectors[source_id]
        except KeyError as exc:
            raise KeyError(f"Unknown or unauthorized data source: {source_id}") from exc

    def config(self, source_id: str) -> DataSourceConfig:
        return self.get(source_id).config

    def redacted_catalog(self) -> list[dict[str, object]]:
        return [connector.config.redacted() for connector in self._connectors.values()]

    async def health_checks(self) -> list[ConnectorHealth]:
        return list(
            await asyncio.gather(*(item.health_check() for item in self._connectors.values()))
        )

    async def close(self) -> None:
        await asyncio.gather(*(item.close() for item in self._connectors.values()))
