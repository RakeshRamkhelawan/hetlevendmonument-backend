"""Unit tests for CVA public router (src/core/api/v1/cva/public_router.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.cva.dependencies import (
    get_cva_agent_registry_dependency,
    get_cva_agent_registry_repository_dependency,
)
from src.core.api.v1.cva.public_router import public_router
from src.core.auth.api_deps import UserResponse, get_current_user_dependency
from src.core.shared.interfaces import ExecutionResult

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_registry() -> AsyncMock:
    reg = AsyncMock()
    reg.register_agent = AsyncMock(return_value=True)
    exec_result = ExecutionResult(
        task_id="task_1",
        success=True,
        result_data={"summary": "done"},
        execution_time=0.1,
    )
    reg.distribute_task = AsyncMock(return_value=exec_result)
    return reg


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    record = MagicMock()
    record.agent_id = "cva_test123"
    record.capabilities = {"functions": ["conversation"]}
    repo.get_registered_agent_by_agent_id = AsyncMock(return_value=record)
    return repo


@pytest.fixture
def mock_user() -> UserResponse:
    return UserResponse(id=123, email="cva@example.com", roles=["editor"], tenant_id=1)


@pytest.fixture
def app(mock_user: UserResponse, mock_registry: AsyncMock, mock_repo: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(public_router)

    application.dependency_overrides[get_current_user_dependency] = lambda: mock_user
    application.dependency_overrides[get_cva_agent_registry_dependency] = lambda: mock_registry
    application.dependency_overrides[get_cva_agent_registry_repository_dependency] = lambda: (
        mock_repo
    )

    for route in application.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            for dep in dependant.dependencies:
                if getattr(dep.call, "__name__", "") == "scope_checker":
                    application.dependency_overrides[dep.call] = lambda: 1

    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_create_managed_cva_agent_success(client: TestClient, mock_registry: AsyncMock) -> None:
    payload = {
        "name": "My Assistant",
        "description": "General assistant",
        "capabilities": ["conversation", "search"],
    }
    response = client.post("/cva/create_agent", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Assistant"
    assert data["status"] == "created"
    assert "id" in data
    assert mock_registry.register_agent.called


def test_create_managed_cva_agent_registration_failure(
    client: TestClient, mock_registry: AsyncMock
) -> None:
    mock_registry.register_agent.return_value = False
    payload = {"name": "Failing Agent"}
    response = client.post("/cva/create_agent", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to initialize CVA agent"


def test_execute_managed_cva_agent_success(
    client: TestClient, mock_repo: AsyncMock, mock_registry: AsyncMock
) -> None:
    payload = {"input": "Hello agent", "context": {"session": "abc"}}
    response = client.post("/cva/execute/cva_test123", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "cva_test123"
    assert data["status"] == "completed"
    assert data["result"]["summary"] == "done"
    assert mock_repo.get_registered_agent_by_agent_id.called
    assert mock_registry.distribute_task.called


def test_execute_managed_cva_agent_not_found(client: TestClient, mock_repo: AsyncMock) -> None:
    mock_repo.get_registered_agent_by_agent_id.return_value = None
    payload = {"input": "Hello"}
    response = client.post("/cva/execute/nonexistent", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "CVA agent not found"
