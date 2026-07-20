from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_jira_pat_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AMA-Agent-Teammate" / "secrets" / "jira_pat.dpapi"
    return Path.home() / ".ama-agent-teammate" / "secrets" / "jira_pat.dpapi"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ama_env: Literal["development", "test", "production"] = "development"
    ama_log_level: str = "INFO"
    ama_api_host: str = "127.0.0.1"
    ama_api_port: int = 8000
    ama_web_origin: str = "http://localhost:5173"
    ama_metadata_database_url: str = "sqlite+aiosqlite:///./var/ama.db"
    ama_checkpoint_database_path: Path = Path("./var/checkpoints.db")
    ama_artifact_root: Path = Path("./var/artifacts")
    ama_demo_database_root: Path = Path("./var/demo-databases")
    ama_provider: Literal["mock", "azure"] = "mock"
    ama_embedding_provider: Literal["mock", "azure"] = "mock"
    ama_skill_registry_root: Path = Path("./skills/registry")
    ama_analysis_skill_root: Path = Path("./skills")
    ama_semantic_metadata_root: Path = Path("./knowledge")
    ama_upload_max_bytes: int = Field(default=10_000_000, gt=0, le=50_000_000)
    ama_conversation_history_max_messages: int = Field(default=12, ge=0, le=40)
    ama_conversation_history_max_characters: int = Field(default=8_000, ge=0, le=30_000)
    ama_model_assisted_routing: bool = True
    ama_analysis_synthesis: bool = True
    ama_knowledge_synthesis_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    ama_development_user_id: str = "local-dev-user"
    ama_development_user_name: str = "Local Developer"

    ama_jira_enabled: bool = False
    ama_jira_base_url: str = "https://jira.xpaas.lenovo.com"
    ama_jira_allowed_projects: str = "LAIR"
    ama_jira_pat_dpapi_path: Path = Field(default_factory=_default_jira_pat_path)
    ama_jira_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ama_jira_max_response_bytes: int = Field(default=1_048_576, ge=1_024, le=5_242_880)
    ama_jira_comment_limit: int = Field(default=20, ge=0, le=100)
    ama_jira_search_max_results: int = Field(default=50, ge=1, le=50)
    ama_jira_write_enabled: bool = False

    ama_super_agent_uat_host: str | None = None
    ama_super_agent_uat_port: int = Field(default=3306, ge=1, le=65535)
    ama_super_agent_uat_database: str = "sa_logs"
    ama_super_agent_uat_username: str | None = None
    ama_super_agent_uat_password: SecretStr | None = None
    ama_super_agent_uat_ssl_ca_path: Path | None = None
    ama_super_agent_uat_allowed_tables: str = "visit_log,turn_log,telemetry_log"
    ama_super_agent_uat_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    ama_super_agent_uat_read_timeout_seconds: int = Field(default=15, ge=1, le=120)
    ama_super_agent_uat_write_timeout_seconds: int = Field(default=10, ge=1, le=60)

    ama_super_agent_uat_query_enabled: bool = False
    ama_super_agent_uat_allow_insecure_transport: bool = False
    ama_super_agent_uat_allow_detail_fields: bool = False
    ama_super_agent_uat_max_rows: int = Field(default=500, ge=1, le=2_000)
    ama_super_agent_uat_max_result_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_auth_mode: Literal["entra_id", "api_key"] = "entra_id"
    azure_openai_api_key: SecretStr | None = None
    azure_openai_deployment_coordinator: str | None = None
    azure_openai_deployment_analyst: str | None = None
    azure_openai_deployment_curator: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    azure_openai_max_retries: int = Field(default=2, ge=0, le=5)
    azure_openai_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    azure_openai_max_output_tokens: int = Field(default=1_024, ge=128, le=16_384)
    azure_openai_token_scope: str = "https://cognitiveservices.azure.com/.default"

    @field_validator(
        "ama_checkpoint_database_path",
        "ama_artifact_root",
        "ama_demo_database_root",
        "ama_skill_registry_root",
        "ama_analysis_skill_root",
        "ama_semantic_metadata_root",
        "ama_jira_pat_dpapi_path",
        mode="before",
    )
    @classmethod
    def expand_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator("ama_super_agent_uat_ssl_ca_path", mode="before")
    @classmethod
    def expand_optional_path(cls, value: str | Path | None) -> Path | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return Path(value).expanduser()

    def super_agent_uat_validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.ama_super_agent_uat_host:
            errors.append("AMA_SUPER_AGENT_UAT_HOST is required")
        if not self.ama_super_agent_uat_username:
            errors.append("AMA_SUPER_AGENT_UAT_USERNAME is required")
        if not self.ama_super_agent_uat_password:
            errors.append("AMA_SUPER_AGENT_UAT_PASSWORD is required")
        allowed_tables = self.super_agent_uat_allowed_table_names()
        if not allowed_tables:
            errors.append("AMA_SUPER_AGENT_UAT_ALLOWED_TABLES must not be empty")
        return errors

    def super_agent_uat_runtime_validation_errors(self) -> list[str]:
        if not self.ama_super_agent_uat_query_enabled:
            return []
        errors = self.super_agent_uat_validation_errors()
        if self.ama_super_agent_uat_allow_insecure_transport and self.ama_env != "development":
            errors.append("AMA_SUPER_AGENT_UAT_ALLOW_INSECURE_TRANSPORT is development-only")
        if self.ama_super_agent_uat_allow_detail_fields and self.ama_env != "development":
            errors.append("AMA_SUPER_AGENT_UAT_ALLOW_DETAIL_FIELDS is development-only")
        return errors

    def super_agent_uat_allowed_table_names(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower()
            for item in self.ama_super_agent_uat_allowed_tables.split(",")
            if item.strip()
        )

    def jira_allowed_project_keys(self) -> frozenset[str]:
        return frozenset(
            item.strip().upper()
            for item in self.ama_jira_allowed_projects.split(",")
            if item.strip()
        )

    def jira_runtime_validation_errors(self) -> list[str]:
        if not self.ama_jira_enabled:
            return []
        errors: list[str] = []
        if not self.ama_jira_base_url.lower().startswith("https://"):
            errors.append("AMA_JIRA_BASE_URL must use HTTPS")
        if not self.jira_allowed_project_keys():
            errors.append("AMA_JIRA_ALLOWED_PROJECTS must not be empty")
        if self.ama_jira_write_enabled and self.ama_env != "development":
            errors.append("AMA_JIRA_WRITE_ENABLED is development-only in the current pilot")
        return errors

    def azure_validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.azure_openai_endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is required")
        if not self.azure_openai_api_version:
            errors.append("AZURE_OPENAI_API_VERSION is required")
        if not self.azure_openai_deployment_coordinator:
            errors.append("AZURE_OPENAI_DEPLOYMENT_COORDINATOR is required")
        if self.azure_openai_auth_mode == "api_key" and not self.azure_openai_api_key:
            errors.append("AZURE_OPENAI_API_KEY is required for api_key auth")
        return errors

    def azure_embedding_validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.azure_openai_endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is required")
        if not self.azure_openai_api_version:
            errors.append("AZURE_OPENAI_API_VERSION is required")
        if not self.azure_openai_embedding_deployment:
            errors.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is required")
        if self.azure_openai_auth_mode == "api_key" and not self.azure_openai_api_key:
            errors.append("AZURE_OPENAI_API_KEY is required for api_key auth")
        return errors

    def ensure_runtime_directories(self) -> None:
        self.ama_checkpoint_database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ama_artifact_root.mkdir(parents=True, exist_ok=True)
        self.ama_demo_database_root.mkdir(parents=True, exist_ok=True)
        self.ama_skill_registry_root.mkdir(parents=True, exist_ok=True)
        if self.ama_metadata_database_url.startswith("sqlite"):
            marker = "///"
            if marker in self.ama_metadata_database_url:
                database_path = self.ama_metadata_database_url.split(marker, 1)[1]
                if database_path and database_path != ":memory:":
                    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
