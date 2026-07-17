from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ama_teammate.storage import analysis_schema as _analysis_schema  # noqa: F401
from ama_teammate.storage import governance_schema as _governance_schema  # noqa: F401
from ama_teammate.storage import learned_metric_schema as _learned_metric_schema  # noqa: F401
from ama_teammate.storage.schema import Base


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()
