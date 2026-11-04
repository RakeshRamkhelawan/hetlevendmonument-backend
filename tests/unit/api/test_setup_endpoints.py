from unittest.mock import mock_open, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.setup_endpoints import router
from src.core.shared.config import reload_settings

app = FastAPI()
app.include_router(router, prefix="/api/v1/setup")
client = TestClient(app)


@pytest.fixture
def enable_setup_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_SETUP_MODE", "true")
    monkeypatch.setenv("SETUP_ARTIFACT_PATH", ".env.bootstrap")
    reload_settings()
    yield
    monkeypatch.delenv("APP_SETUP_MODE", raising=False)
    monkeypatch.delenv("SETUP_ARTIFACT_PATH", raising=False)
    reload_settings()


def test_setup_init_returns_404_when_setup_mode_disabled():
    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 404


@patch("src.core.services.setup_service.SetupService.validate_openai_key")
@patch("builtins.open", new_callable=mock_open)
def test_setup_init_happy_path(mock_file, mock_validate, enable_setup_mode):
    mock_validate.return_value = True

    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 200
    mock_validate.assert_called_once_with("sk-valid-key")
    mock_file.assert_called()  # Verifies .env was opened for writing
    assert response.json()["artifact_name"] == ".env.bootstrap"


@patch("src.core.services.setup_service.SetupService.validate_openai_key")
def test_setup_init_invalid_key(mock_validate, enable_setup_mode):
    mock_validate.return_value = False

    payload = {
        "openai_api_key": "sk-invalid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 400
    assert "Invalid OpenAI API Key" in response.json()["detail"]


@patch("src.core.services.setup_service.SetupService.validate_openai_key")
@patch("builtins.open")
def test_setup_init_file_permission_error(mock_open_file, mock_validate, enable_setup_mode):
    mock_validate.return_value = True
    mock_open_file.side_effect = PermissionError("Permission denied")

    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 500
    assert response.json()["detail"] == "Setup initialization failed"


@patch("src.core.services.setup_service.SetupService.validate_openai_key")
def test_setup_init_rejects_unsafe_artifact_path(
    mock_validate,
    monkeypatch: pytest.MonkeyPatch,
    enable_setup_mode,
):
    mock_validate.return_value = True
    monkeypatch.setenv("SETUP_ARTIFACT_PATH", ".env")
    reload_settings()

    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 400
    assert "bootstrap artifact" in response.json()["detail"]


@patch("src.core.services.setup_service.SetupService.validate_openai_key")
def test_setup_init_returns_409_when_bootstrap_already_exists(
    mock_validate,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    enable_setup_mode,
):
    mock_validate.return_value = True
    monkeypatch.chdir(tmp_path)

    artifact_path = tmp_path / ".env.bootstrap"
    artifact_path.write_text("OPENAI_API_KEY=existing\n", encoding="utf-8")

    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "Setup has already been initialized"


def test_setup_init_rejects_oversized_tenant_name(enable_setup_mode):
    payload = {
        "openai_api_key": "sk-valid-key",
        "tenant_name": "A" * 201,
        "admin_email": "admin@acme.com",
        "smtp_host": "smtp.mailgun.org",
    }

    response = client.post("/api/v1/setup/init", json=payload)

    assert response.status_code == 422
