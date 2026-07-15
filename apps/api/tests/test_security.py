from __future__ import annotations

from ama_teammate.config import Settings
from ama_teammate.logging import redact
from ama_teammate.providers.factory import create_provider_bundle


def test_redaction_removes_secret_values() -> None:
    value = "api_key=abc123 authorization:BearerSecret password=hunter2"
    redacted = redact(value)
    assert "abc123" not in redacted
    assert "BearerSecret" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_azure_configuration_reports_missing_fields_without_secrets() -> None:
    settings = Settings(_env_file=None, ama_provider="azure", azure_openai_auth_mode="api_key")
    errors = settings.azure_validation_errors()
    assert "AZURE_OPENAI_ENDPOINT is required" in errors
    assert "AZURE_OPENAI_API_KEY is required for api_key auth" in errors
    bundle = create_provider_bundle(settings)
    assert bundle.provider.name == "azure"
    assert bundle.coordinator.deployment == "unconfigured"
