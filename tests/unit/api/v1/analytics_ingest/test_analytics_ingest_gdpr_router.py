"""Unit tests for analytics ingest GDPR router (src/core/api/v1/analytics_ingest/gdpr_router.py)."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.analytics_ingest.dependencies import (
    UserResponse,
    get_current_tenant_id,
    get_current_user,
    get_db,
)
from src.core.api.v1.analytics_ingest.gdpr_router import router

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> UserResponse:
    return UserResponse(id=123, email="user@example.com", roles=["user"], tenant_id=1)


@pytest.fixture
def app(mock_db: AsyncMock, mock_user: UserResponse) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_user] = lambda: mock_user
    application.dependency_overrides[get_current_tenant_id] = lambda: "tenant_1"
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_export_user_data_success(client: TestClient, mock_db: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    response = client.post("/events/export")
    assert response.status_code == 200
    data = response.json()
    assert data["userId"] == "123"
    assert data["tenantId"] == "tenant_1"
    assert "events" in data
    assert "sessions" in data
    assert "summary" in data


def test_export_user_data_error_raises_500(client: TestClient, mock_db: AsyncMock) -> None:
    mock_db.execute.side_effect = RuntimeError("DB connection error")

    response = client.post("/events/export")
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to export user data"


def test_delete_user_data_success(client: TestClient, mock_db: AsyncMock) -> None:
    mock_del_result = MagicMock()
    mock_del_result.rowcount = 5

    mock_sess_result = MagicMock()
    mock_sess = MagicMock()
    mock_sess_result.scalars.return_value.all.return_value = [mock_sess]

    mock_db.execute.side_effect = [mock_del_result, mock_sess_result]

    response = client.delete("/events/user")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "User data deleted successfully"
    assert mock_db.commit.called
    assert mock_sess.is_active is False


def test_delete_user_data_error_raises_500(client: TestClient, mock_db: AsyncMock) -> None:
    mock_db.execute.side_effect = RuntimeError("DB delete error")

    response = client.delete("/events/user")
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to delete user data"
    assert mock_db.rollback.called
