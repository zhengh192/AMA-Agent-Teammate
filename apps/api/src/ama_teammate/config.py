from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ama_semantic_metadata_root: Path = Path("./knowledge")
    ama_upload_max_bytes: int = Field(default=10_000_000, gt=0, le=50_000_000)
    ama_development_user_id: str = "local-dev-user"
    ama_development_user_name: str = "Local Developer"

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
    azure_openai_token_scope: str = "https://cognitiveservices.azure.com/.default"

    @field_validator(
        "ama_checkpoint_database_path",
        "ama_artifact_root",
        "ama_demo_database_root",
        "ama_skill_registry_root",
        "ama_semantic_metadata_root",
        mode="before",
    )
    @classmethod
    def expand_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

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
