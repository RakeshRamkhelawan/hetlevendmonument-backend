"""Unit tests for privacy DSAR router (src/core/api/v1/privacy/dsar_router.py)."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.privacy.dependencies import get_current_user, get_db
from src.core.api.v1.privacy.dsar_router import dsar_router
from src.core.models.rbac_models import User

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 123
    user.email = "privacy.user@example.com"
    user.tenant_id = 1
    return user


@pytest.fixture
def app(mock_session: AsyncMock, mock_user: MagicMock) -> FastAPI:
    application = FastAPI()
    application.include_router(dsar_router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_user] = lambda: mock_user
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_export_my_data_success(client: TestClient, mock_session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    response = client.get("/export")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "user_data_export_" in response.headers["content-disposition"]
    data = response.json()
    assert "user" in data
    assert data["user"]["id"] == 123


def test_forget_me_success(client: TestClient, mock_session: AsyncMock) -> None:
    payload = {
        "confirm_email": "privacy.user@example.com",
        "reason": "leaving platform",
    }
    response = client.post("/forget", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "beheerder van uw bedrijf" in data["message"]
    assert mock_session.commit.called


def test_forget_me_message_is_dutch_and_does_not_point_to_support(
    client: TestClient,
) -> None:
    payload = {"confirm_email": "privacy.user@example.com"}
    message = client.post("/forget", json=payload).json()["message"]
    assert "support" not in message.lower()


def test_forget_me_email_mismatch_raises_400(client: TestClient) -> None:
    payload = {
        "confirm_email": "wrong.email@example.com",
        "reason": "leaving platform",
    }
    response = client.post("/forget", json=payload)
    assert response.status_code == 400
    assert "Email confirmation does not match" in response.json()["detail"]


def test_forget_me_db_error_raises_500(client: TestClient, mock_session: AsyncMock) -> None:
    mock_session.execute.side_effect = RuntimeError("DB deletion error")
    payload = {
        "confirm_email": "privacy.user@example.com",
    }
    response = client.post("/forget", json=payload)
    assert response.status_code == 500
    assert "An error occurred during data deletion" in response.json()["detail"]
    assert mock_session.rollback.called
