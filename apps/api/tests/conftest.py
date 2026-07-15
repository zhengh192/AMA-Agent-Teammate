from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ama_teammate.config import Settings
from ama_teammate.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ama_env="test",
        ama_provider="mock",
        ama_metadata_database_url=f"sqlite+aiosqlite:///{(tmp_path / 'ama.db').as_posix()}",
        ama_checkpoint_database_path=tmp_path / "checkpoints.db",
        ama_artifact_root=tmp_path / "artifacts",
        ama_demo_database_root=tmp_path / "demo-databases",
        ama_skill_registry_root=tmp_path / "skills",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
