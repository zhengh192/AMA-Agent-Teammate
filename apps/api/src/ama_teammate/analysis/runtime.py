from __future__ import annotations

from dataclasses import dataclass

from ama_teammate.analysis.artifacts import CSVArtifactWriter
from ama_teammate.analysis.charts import ChartBuilder, PlotlySpecValidator
from ama_teammate.analysis.engine import ControlledAnalysisEngine
from ama_teammate.analysis.join import BoundedDuckDBJoiner
from ama_teammate.analysis.json_artifacts import JSONArtifactStore
from ama_teammate.analysis.planner import AnalysisPlanner
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry
from ama_teammate.config import Settings
from ama_teammate.data_access.base import ReadOnlyConnector
from ama_teammate.data_access.demo import (
    DemoDatabaseManager,
    DemoReadOnlyConnector,
    demo_source_configs,
)
from ama_teammate.data_access.mysql import MySQLConnectionOptions, MySQLReadOnlyConnector
from ama_teammate.data_access.registry import ConnectorRegistry
from ama_teammate.evidence.validator import EvidenceValidator
from ama_teammate.learned_metrics.service import LearnedMetricService
from ama_teammate.providers.factory import ProviderBundle
from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry
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
    semantic_registry: SemanticMetadataRegistry,
    skill_registry: AnalysisSkillRegistry,
) -> AnalysisRuntime:
    manager = DemoDatabaseManager(settings.ama_demo_database_root)
    await manager.initialize()
    connectors: list[ReadOnlyConnector] = [
        DemoReadOnlyConnector(config, manager.path_for(config.id))
        for config in demo_source_configs()
    ]
    if settings.ama_super_agent_uat_query_enabled:
        errors = settings.super_agent_uat_runtime_validation_errors()
        if errors:
            raise ValueError("; ".join(errors))
        assert settings.ama_super_agent_uat_host is not None
        assert settings.ama_super_agent_uat_username is not None
        assert settings.ama_super_agent_uat_password is not None
        options = MySQLConnectionOptions(
            host=settings.ama_super_agent_uat_host,
            port=settings.ama_super_agent_uat_port,
            username=settings.ama_super_agent_uat_username,
            password=settings.ama_super_agent_uat_password,
            database=settings.ama_super_agent_uat_database,
            allowed_tables=settings.super_agent_uat_allowed_table_names(),
            ssl_ca_path=settings.ama_super_agent_uat_ssl_ca_path,
            allow_insecure_transport=settings.ama_super_agent_uat_allow_insecure_transport,
            allow_detail_fields=settings.ama_super_agent_uat_allow_detail_fields,
            connect_timeout_seconds=settings.ama_super_agent_uat_connect_timeout_seconds,
            read_timeout_seconds=settings.ama_super_agent_uat_read_timeout_seconds,
            write_timeout_seconds=settings.ama_super_agent_uat_write_timeout_seconds,
            max_rows=settings.ama_super_agent_uat_max_rows,
            max_result_bytes=settings.ama_super_agent_uat_max_result_bytes,
            query_enabled=True,
        )
        uat_connector, _ = await MySQLReadOnlyConnector.discover(options)
        connectors.append(uat_connector)
    gateway = SQLSafetyGateway()
    registry = ConnectorRegistry(connectors)
    analysis_repository = AnalysisRepository(database)
    learned_metrics = LearnedMetricService(database, registry, repository, semantic_registry)
    planner = AnalysisPlanner(
        providers,
        registry,
        gateway,
        semantic_registry,
        skill_registry,
        learned_metrics,
        share_skill_instructions_with_model=settings.ama_share_skill_instructions_with_model,
    )
    service = AnalysisService(
        planner=planner,
        registry=registry,
        analysis_repository=analysis_repository,
        learned_metrics=learned_metrics,
        repository=repository,
        joiner=BoundedDuckDBJoiner(),
        engine=ControlledAnalysisEngine(),
        chart_builder=ChartBuilder(PlotlySpecValidator()),
        evidence_validator=EvidenceValidator(),
        csv_writer=CSVArtifactWriter(settings.ama_artifact_root),
        json_store=JSONArtifactStore(settings.ama_artifact_root),
    )
    return AnalysisRuntime(registry=registry, service=service)
