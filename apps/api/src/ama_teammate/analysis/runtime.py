from __future__ import annotations

from dataclasses import dataclass

from ama_teammate.analysis.artifacts import CSVArtifactWriter
from ama_teammate.analysis.charts import ChartBuilder, PlotlySpecValidator
from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.join import BoundedDuckDBJoiner
from ama_teammate.analysis.json_artifacts import JSONArtifactStore
from ama_teammate.analysis.planner import AnalysisPlanner
from ama_teammate.config import Settings
from ama_teammate.data_access.demo import (
    DemoDatabaseManager,
    DemoReadOnlyConnector,
    demo_source_configs,
)
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.evidence.validator import EvidenceValidator
from ama_teammate.providers.factory import ProviderBundle
from ama_teammate.services.analysis import AnalysisService
from ama_teammate.sql_policy.gateway import SQLSafetyGateway
from ama_teammate.storage.analysis_repository import AnalysisRepository
from ama_teammate.storage.database import Database
from ama_teammate.storage.repositories import Repository


@dataclass(slots=True)
class AnalysisRuntime:
    registry: ConnectorRegistry
    service: AnalysisService


async def create_analysis_runtime(
    settings: Settings,
    database: Database,
    repository: Repository,
    providers: ProviderBundle,
) -> AnalysisRuntime:
    manager = DemoDatabaseManager(settings.ama_demo_database_root)
    await manager.initialize()
    registry = ConnectorRegistry(
        [
            DemoReadOnlyConnector(config, manager.path_for(config.id))
            for config in demo_source_configs()
        ]
    )
    gateway = SQLSafetyGateway()
    planner = AnalysisPlanner(providers, registry, gateway)
    service = AnalysisService(
        planner=planner,
        registry=registry,
        analysis_repository=AnalysisRepository(database),
        repository=repository,
        joiner=BoundedDuckDBJoiner(),
        engine=ControlledAnalysisEngine(),
        chart_builder=ChartBuilder(PlotlySpecValidator()),
        evidence_validator=EvidenceValidator(),
        csv_writer=CSVArtifactWriter(settings.ama_artifact_root),
        json_store=JSONArtifactStore(settings.ama_artifact_root),
    )
    return AnalysisRuntime(registry=registry, service=service)
