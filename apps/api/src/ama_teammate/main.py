from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ama_teammate.analysis.runtime import create_analysis_runtime
from ama_teammate.api.routes_analysis import router as analysis_router
from ama_teammate.api.routes_chat import router as chat_router
from ama_teammate.api.routes_governance import router as governance_router
from ama_teammate.api.routes_health import router as health_router
from ama_teammate.api.routes_sessions import router as sessions_router
from ama_teammate.config import Settings, get_settings
from ama_teammate.errors import AppError, app_error_handler, unhandled_error_handler
from ama_teammate.governance.service import GovernanceService
from ama_teammate.logging import configure_logging
from ama_teammate.orchestration.graph import GraphRuntime, build_graph
from ama_teammate.providers.embeddings import create_embedding_provider
from ama_teammate.providers.factory import create_provider_bundle
from ama_teammate.services.phase3_chat import PhaseThreeChatService
from ama_teammate.storage.database import Database
from ama_teammate.storage.repositories import Repository


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.ama_log_level)
        resolved_settings.ensure_runtime_directories()
        database = Database(resolved_settings.ama_metadata_database_url)
        await database.initialize()
        repository = Repository(database)
        await repository.ensure_user(
            resolved_settings.ama_development_user_id,
            resolved_settings.ama_development_user_name,
        )
        checkpoint_connection = await aiosqlite.connect(
            str(resolved_settings.ama_checkpoint_database_path)
        )
        checkpointer = AsyncSqliteSaver(checkpoint_connection)
        await checkpointer.setup()
        providers = create_provider_bundle(resolved_settings)
        embedding_provider = create_embedding_provider(resolved_settings)
        analysis_runtime = await create_analysis_runtime(
            resolved_settings, database, repository, providers
        )
        graph = GraphRuntime(build_graph(checkpointer, analysis_runtime.service))
        app.state.settings = resolved_settings
        app.state.database = database
        app.state.repository = repository
        app.state.graph = graph
        app.state.providers = providers
        app.state.analysis_service = analysis_runtime.service
        governance_service = GovernanceService(
            resolved_settings, database, repository, embedding_provider
        )
        app.state.governance_service = governance_service
        app.state.connector_registry = analysis_runtime.registry
        app.state.chat_service = PhaseThreeChatService(
            settings=resolved_settings,
            repository=repository,
            graph=graph,
            providers=providers,
            analysis_service=analysis_runtime.service,
            governance_service=governance_service,
        )
        try:
            yield
        finally:
            await analysis_runtime.registry.close()
            await embedding_provider.close()
            await providers.provider.close()
            await checkpoint_connection.close()
            await database.close()

    app = FastAPI(
        title="AMA Data Analysis Teammate API",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.ama_web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health_router, prefix="/api")
    app.include_router(analysis_router, prefix="/api")
    app.include_router(governance_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    return app


app = create_app()
