"""Unit tests for compliance score router (src/core/api/v1/compliance/score_router.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.compliance.dependencies import (
    ComplianceScoreCalculator,
    ComplianceScoreResult,
    get_current_user,
    get_score_service,
)
from src.core.api.v1.compliance.score_router import score_router
from src.core.models.rbac_models import User

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 123
    user.email = "compliance@example.com"
    user.tenant_id = 1
    return user


@pytest.fixture
def mock_calculator() -> AsyncMock:
    calc = AsyncMock(spec=ComplianceScoreCalculator)
    score_res = ComplianceScoreResult(
        overall_score=88.5,
        gdpr_score=90.0,
        ai_act_score=85.0,
        audit_score=92.0,
        calculated_at=datetime.now(timezone.utc),
        tenant_id=1,
    )
    calc.calculate_overall_score = AsyncMock(return_value=score_res)
    calc.get_score_history = AsyncMock(return_value=[score_res])
    return calc


@pytest.fixture
def app(mock_user: MagicMock, mock_calculator: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(score_router)

    application.dependency_overrides[get_current_user] = lambda: mock_user
    application.dependency_overrides[get_score_service] = lambda: mock_calculator
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_get_compliance_score_success(client: TestClient, mock_calculator: AsyncMock) -> None:
    response = client.get("/score")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_score"] == 88.5
    assert data["gdpr_score"] == 90.0
    assert data["ai_act_score"] == 85.0
    assert data["tenant_id"] == 1
    assert mock_calculator.calculate_overall_score.called


def test_get_compliance_score_error_raises_500(client: TestClient, mock_calculator: AsyncMock) -> None:
    mock_calculator.calculate_overall_score.side_effect = RuntimeError("Score computation failed")
    response = client.get("/score")
    assert response.status_code == 500
    assert "Failed to calculate compliance score" in response.json()["detail"]


def test_get_compliance_score_history_success(client: TestClient, mock_calculator: AsyncMock) -> None:
    response = client.get("/score/history?days=30&limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["total_count"] == 1
    assert data["days_requested"] == 30
    assert len(data["history"]) == 1
    assert data["history"][0]["overall_score"] == 88.5
    assert mock_calculator.get_score_history.called


def test_get_compliance_score_history_error_raises_500(client: TestClient, mock_calculator: AsyncMock) -> None:
    mock_calculator.get_score_history.side_effect = RuntimeError("History retrieval failed")
    response = client.get("/score/history")
    assert response.status_code == 500
    assert "Failed to retrieve compliance score history" in response.json()["detail"]
