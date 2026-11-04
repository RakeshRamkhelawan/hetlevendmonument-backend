"""Security regression tests for setup endpoint lockdown."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.core.api.public_endpoints import PublicEndpointRegistry
from src.core.api.registries.integrations import register as _register_billing_integrations
from src.core.services.setup_service import SetupService
from src.core.shared.config import reload_settings


@pytest.fixture(autouse=True)
def reset_setup_mode(monkeypatch: pytest.MonkeyPatch):
    """Reset setup-mode related environment variables around each test."""
    monkeypatch.delenv("APP_SETUP_MODE", raising=False)
    monkeypatch.delenv("SETUP_ARTIFACT_PATH", raising=False)
    reload_settings()
    yield
    monkeypatch.delenv("APP_SETUP_MODE", raising=False)
    monkeypatch.delenv("SETUP_ARTIFACT_PATH", raising=False)
    reload_settings()


@pytest.mark.security
def test_setup_init_is_not_public_by_default() -> None:
    """Normal runtime must not treat the setup endpoint as a public path."""
    assert PublicEndpointRegistry.is_public("/api/v1/setup/init") is False


@pytest.mark.security
def test_setup_router_is_absent_by_default_and_present_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup routes should only be mounted when explicit bootstrap mode is enabled."""
    disabled_app = FastAPI()
    _register_billing_integrations(disabled_app)

    disabled_paths = {route.path for route in disabled_app.routes}
    assert "/api/v1/setup/init" not in disabled_paths

    monkeypatch.setenv("APP_SETUP_MODE", "true")
    reload_settings()

    enabled_app = FastAPI()
    _register_billing_integrations(enabled_app)

    enabled_paths = {route.path for route in enabled_app.routes}
    assert "/api/v1/setup/init" in enabled_paths


@pytest.mark.security
def test_setup_init_becomes_public_only_in_explicit_setup_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap mode should make the setup endpoint reachable through public-route middleware."""
    assert PublicEndpointRegistry.is_public("/api/v1/setup/init") is False

    monkeypatch.setenv("APP_SETUP_MODE", "true")
    reload_settings()

    assert PublicEndpointRegistry.is_public("/api/v1/setup/init") is True


@pytest.mark.security
def test_setup_mode_does_not_make_arbitrary_setup_routes_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the reviewed setup init route may bypass auth during setup mode."""
    monkeypatch.setenv("APP_SETUP_MODE", "true")
    reload_settings()

    assert PublicEndpointRegistry.is_public("/api/v1/setup/init") is True
    assert PublicEndpointRegistry.is_public("/api/v1/setup/other") is False


@pytest.mark.security
def test_setup_service_refuses_live_env_writes_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal runtime must not allow setup code to append directly to a live .env file."""
    monkeypatch.chdir(tmp_path)

    service = SetupService()

    with pytest.raises(PermissionError):
        service.write_env_file(
            {
                "OPENAI_API_KEY": "sk-test",
                "INITIAL_TENANT_NAME": "Acme Corp",
                "INITIAL_ADMIN_EMAIL": "admin@example.com",
            }
        )

    assert not (tmp_path / ".env").exists()


@pytest.mark.security
@pytest.mark.parametrize(
    "artifact_path",
    [
        ".env",
        ".env.production",
        "nested/.env.bootstrap",
        "../.env.bootstrap",
    ],
)
def test_setup_service_rejects_unsafe_artifact_paths_when_enabled(
    artifact_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup mode must still reject unsafe artifact-path overrides."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_SETUP_MODE", "true")
    monkeypatch.setenv("SETUP_ARTIFACT_PATH", artifact_path)
    reload_settings()

    service = SetupService()

    with pytest.raises(ValueError, match="bootstrap artifact"):
        service.write_env_file(
            {
                "OPENAI_API_KEY": "sk-test",
                "INITIAL_TENANT_NAME": "Acme Corp",
                "INITIAL_ADMIN_EMAIL": "admin@example.com",
            }
        )


@pytest.mark.security
def test_setup_service_allows_bootstrap_artifact_only_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap artifact writes must be single-use to prevent replay and append abuse."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_SETUP_MODE", "true")
    monkeypatch.setenv("SETUP_ARTIFACT_PATH", ".env.bootstrap")
    reload_settings()

    service = SetupService()
    configs = {
        "OPENAI_API_KEY": "sk-test",
        "INITIAL_TENANT_NAME": "Acme Corp",
        "INITIAL_ADMIN_EMAIL": "admin@example.com",
    }

    service.write_env_file(configs)

    with pytest.raises(FileExistsError):
        service.write_env_file(configs)
