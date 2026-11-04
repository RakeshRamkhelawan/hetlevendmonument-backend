"""Unit tests for AI features learning router (src/core/api/v1/ai_features/learning_router.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine
from src.core.api.v1.ai_features.learning_router import router
from src.core.auth.api_deps import UserResponse, get_current_user

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_engine() -> AsyncMock:
    mock = AsyncMock(spec=AdaptiveLearningEngine)
    mock.record_event = AsyncMock()

    mock_insight = MagicMock()
    mock_insight.to_dict.return_value = {
        "id": "ins_1",
        "pattern_type": "interaction",
        "confidence": 0.85,
        "description": "User prefers concise answers",
    }
    mock_insight.confidence = 0.85
    mock_insight.pattern_type = "interaction"

    mock.get_insights = AsyncMock(return_value=[mock_insight])
    return mock


@pytest.fixture
def mock_user() -> UserResponse:
    return UserResponse(id=123, email="user@example.com", roles=["user"], tenant_id=1)


@pytest.fixture
def app(mock_user: UserResponse, mock_engine: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    application.dependency_overrides[get_current_user] = lambda: mock_user
    for route in application.routes:
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if getattr(dep.call, "__name__", "") == "scope_checker":
                    application.dependency_overrides[dep.call] = lambda: 1
                elif dep.name == "engine":
                    application.dependency_overrides[dep.call] = lambda: mock_engine

    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_record_learning_event_success(client: TestClient, mock_engine: AsyncMock) -> None:
    payload = {
        "event_type": "feedback_received",
        "context": {"source": "test_suite"},
        "outcome": "positive",
        "confidence": 0.9,
        "metadata": {"metrics": {"score": 1.0}},
    }
    response = client.post("/learning/event", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Learning event recorded successfully"
    assert data["event_type"] == "feedback_received"
    assert mock_engine.record_event.called


def test_record_learning_event_error_raises_500(client: TestClient, mock_engine: AsyncMock) -> None:
    mock_engine.record_event.side_effect = RuntimeError("Engine failure")
    payload = {
        "event_type": "user_feedback",
        "context": {"source": "test_suite"},
    }
    response = client.post("/learning/event", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to record event"


def test_get_learning_insights_success(client: TestClient, mock_engine: AsyncMock) -> None:
    response = client.get("/learning/insights?category=interaction&min_confidence=0.8&limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "insights" in data
    assert len(data["insights"]) == 1
    assert data["insights"][0]["pattern_type"] == "interaction"
    assert data["summary"]["total_insights"] == 1
    assert data["summary"]["average_confidence"] == 0.85
    assert mock_engine.get_insights.called


def test_get_learning_insights_error_raises_500(client: TestClient, mock_engine: AsyncMock) -> None:
    mock_engine.get_insights.side_effect = RuntimeError("Failure fetching insights")
    response = client.get("/learning/insights")
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to get insights"
