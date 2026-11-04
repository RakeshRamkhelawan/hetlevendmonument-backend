"""Unit tests for admin LLM providers router (src/core/api/v1/admin/llm_providers_router.py)."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.admin.dependencies import get_db, require_admin_role
from src.core.api.v1.admin.llm_providers_router import router
from src.core.auth.auth_service import UserResponse

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_admin() -> UserResponse:
    return UserResponse(id=1, email="admin@example.com", roles=["admin"], tenant_id=1)


@pytest.fixture
def app(mock_db: AsyncMock, mock_admin: UserResponse) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[require_admin_role] = lambda: mock_admin
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_toon_llm_providers_success(client: TestClient) -> None:
    mock_service = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = "prov_1"
    mock_row.volgorde = 1
    mock_row.naam = "OpenAI Production"
    mock_row.base_url = "https://api.openai.com/v1"
    mock_row.model = "gpt-4o"
    mock_row.heeft_sleutel = True
    mock_row.actief = True

    mock_service.toon = AsyncMock(return_value=[mock_row])

    with patch("src.core.api.v1.admin.llm_providers_router.bouw_llm_provider_service", return_value=mock_service):
        response = client.get("/admin/llm-providers?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["naam"] == "OpenAI Production"
    assert data["meta"]["total"] == 1


def test_richt_llm_provider_in_success(client: TestClient) -> None:
    mock_service = AsyncMock()
    mock_service.configureer = AsyncMock(return_value="prov_new_123")

    payload = {
        "volgorde": 1,
        "naam": "Anthropic Claude",
        "base_url": "https://api.anthropic.com",
        "model": "claude-3-5-sonnet-20241022",
        "api_key": "sk-ant-test",
        "actief": True,
    }

    with patch("src.core.api.v1.admin.llm_providers_router.bouw_llm_provider_service", return_value=mock_service), \
         patch("src.core.api.v1.admin.llm_providers_router.schrijf_llm_provider_audit", AsyncMock()):
        response = client.post("/admin/llm-providers", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == "prov_new_123"
    assert mock_service.configureer.called


def test_richt_llm_provider_in_forbidden_external_raises_403(client: TestClient) -> None:
    mock_service = AsyncMock()
    from src.core.api.v1.admin.dependencies import llm_provider_fouten
    extern_verboden, _ = llm_provider_fouten()
    mock_service.configureer = AsyncMock(side_effect=extern_verboden("Externe providers niet toegestaan"))

    payload = {
        "volgorde": 2,
        "naam": "External Provider",
        "base_url": "https://external.example.com",
        "model": "ext-model",
        "actief": True,
    }

    with patch("src.core.api.v1.admin.llm_providers_router.bouw_llm_provider_service", return_value=mock_service), \
         patch("src.core.api.v1.admin.llm_providers_router.schrijf_llm_provider_audit", AsyncMock()):
        response = client.post("/admin/llm-providers", json=payload)

    assert response.status_code == 403
