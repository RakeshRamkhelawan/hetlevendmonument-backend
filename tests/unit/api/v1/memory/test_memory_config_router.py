"""Unit tests for memory config router (src/core/api/v1/memory/config_router.py)."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.dependencies import get_current_user, get_db
from src.core.api.v1.memory.config_router import router
from src.core.api.v1.memory.dependencies import get_tenant
from src.core.api.v1.memory.schemas import EmbeddingModel, RAGConfig
from src.core.auth.auth_service import UserResponse

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(mock_db: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_tenant] = lambda: 1
    # Sinds de nazorg eisen /config GET en PUT `require_admin_user`: de fixture is een beheerder.
    application.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=123, email="beheer@example.com", roles=["admin"], tenant_id=1
    )

    for route in application.routes:
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if getattr(dep.call, "__name__", "") == "scope_checker":
                    application.dependency_overrides[dep.call] = lambda: {"id": 123, "sub": "123"}

    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_get_config_success(client: TestClient) -> None:
    default_config = RAGConfig()
    with patch("src.core.api.v1.memory.config_router.get_tenant_config", return_value=default_config):
        response = client.get("/config")

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == 1
    assert data["message"] == "RAG configuration retrieved successfully"
    assert "config" in data


def test_get_config_missing_tenant_raises_400(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_tenant] = lambda: None
    response = client.get("/config")
    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant context required."


def test_update_config_success(client: TestClient) -> None:
    current_config = RAGConfig(embedding_model=EmbeddingModel.OPENAI_3_SMALL)
    with patch("src.core.api.v1.memory.config_router.get_tenant_config", return_value=current_config), \
         patch("src.core.api.v1.memory.config_router.save_tenant_config") as mock_save:
        payload = {
            "embedding_model": "text-embedding-3-large",
            "embedding_dimensions": 3072,
            "chunking": {"strategy": "recursive", "chunk_size": 1000, "chunk_overlap": 100, "min_chunk_size": 100},
            "retrieval": {"top_k": 10, "similarity_threshold": 0.8},
            "index_name": "custom_index",
        }
        response = client.put("/config", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == 1
    assert "Embedding model changed" in data["message"]
    assert mock_save.called


def test_update_config_missing_tenant_raises_400(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_tenant] = lambda: None
    payload = {
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "chunking": {"strategy": "recursive", "chunk_size": 512, "chunk_overlap": 50, "min_chunk_size": 100},
        "retrieval": {"top_k": 5, "similarity_threshold": 0.7},
        "index_name": "default",
    }
    response = client.put("/config", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant context required."


@pytest.mark.parametrize("methode", ["get", "put"])
def test_config_niet_beheerder_krijgt_403(app: FastAPI, client: TestClient, methode: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=124, email="gewoon@example.com", roles=["user"], tenant_id=1
    )
    payload = {
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "chunking": {"strategy": "recursive", "chunk_size": 512, "chunk_overlap": 50, "min_chunk_size": 100},
        "retrieval": {"top_k": 5, "similarity_threshold": 0.7},
        "index_name": "default",
    }

    response = client.request(methode, "/config", json=payload if methode == "put" else None)

    assert (response.status_code, response.json()["detail"]) == (403, "Admin privileges required")
