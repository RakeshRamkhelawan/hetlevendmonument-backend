"""Unit tests for AI features system router (src/core/api/v1/ai_features/system_router.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine
from src.core.ai.intelligent_routing import IntelligentRouter
from src.core.ai.predictive_analytics import PredictiveAnalyticsEngine
from src.core.api.v1.ai_features.system_router import router
from src.core.api.dependencies import get_current_user as get_current_user_voor_rolcontrole
from src.core.auth.api_deps import UserResponse, get_current_user

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_adaptive_engine() -> AsyncMock:
    mock = AsyncMock(spec=AdaptiveLearningEngine)
    mock.get_event_count.return_value = 42
    mock.get_insights.return_value = ["insight1", "insight2"]
    return mock


@pytest.fixture
def mock_router() -> AsyncMock:
    mock = AsyncMock(spec=IntelligentRouter)
    mock.get_available_routes.return_value = ["route_a", "route_b"]
    mock.get_average_decision_time.return_value = 14.5
    return mock


@pytest.fixture
def mock_predictive() -> AsyncMock:
    mock = AsyncMock(spec=PredictiveAnalyticsEngine)
    mock.get_active_models_count.return_value = 3
    mock.get_average_confidence.return_value = 0.92
    return mock


@pytest.fixture
def mock_user() -> UserResponse:
    """Beheerder: `/system/status` eist sinds de nazorg `require_admin_user` (403 voor anderen)."""
    return UserResponse(id=123, email="beheer@example.com", roles=["admin"], tenant_id=1)


@pytest.fixture
def app(
    mock_user: UserResponse,
    mock_adaptive_engine: AsyncMock,
    mock_router: AsyncMock,
    mock_predictive: AsyncMock,
) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    application.dependency_overrides[get_current_user] = lambda: mock_user
    application.dependency_overrides[get_current_user_voor_rolcontrole] = lambda: mock_user
    for route in application.routes:
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if getattr(dep.call, "__name__", "") == "scope_checker":
                    application.dependency_overrides[dep.call] = lambda: 1
                elif dep.name == "adaptive_learning_engine":
                    application.dependency_overrides[dep.call] = lambda: mock_adaptive_engine
                elif dep.name == "intelligent_router":
                    application.dependency_overrides[dep.call] = lambda: mock_router
                elif dep.name == "predictive_analytics":
                    application.dependency_overrides[dep.call] = lambda: mock_predictive

    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_get_ai_system_status_success(client: TestClient) -> None:
    response = client.get("/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "components" in data
    assert data["components"]["adaptive_learning"]["events_processed"] == 42
    assert data["components"]["adaptive_learning"]["insights_available"] == 2
    assert data["components"]["intelligent_routing"]["routes_available"] == ["route_a", "route_b"]
    assert data["components"]["intelligent_routing"]["average_decision_time_ms"] == 14.5
    assert data["components"]["predictive_analytics"]["models_active"] == 3
    assert data["components"]["predictive_analytics"]["average_prediction_confidence"] == 0.92


def test_get_ai_system_status_error_raises_500(
    client: TestClient,
    mock_adaptive_engine: AsyncMock,
) -> None:
    mock_adaptive_engine.get_event_count.side_effect = RuntimeError("DB down")

    response = client.get("/system/status")
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to get system status"


def test_get_ai_capabilities_success(client: TestClient) -> None:
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "capabilities" in data
    assert "adaptive_learning" in data["capabilities"]
    assert "intelligent_routing" in data["capabilities"]
    assert "predictive_analytics" in data["capabilities"]
    assert data["version"] == "1.0.0"


def test_get_ai_system_status_niet_beheerder_krijgt_403(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_current_user_voor_rolcontrole] = lambda: UserResponse(
        id=124, email="gewoon@example.com", roles=["user"], tenant_id=1
    )

    response = client.get("/system/status")

    assert (response.status_code, response.json()["detail"]) == (403, "Admin privileges required")
