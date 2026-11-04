"""
Integration tests for prediction endpoints with mocking.
Uses TestClient from conftest.py with mocked predictive engine.
Philosophy: Mock the engine but test real API endpoints.

Author: Test Engineer
Date: 2025-11-22
Coverage Target: 90%+ with mocked predictive engine
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


def get_error_message(data: dict) -> str:
    """
    Extract error message from API response - supports both formats.

    Format 1 (HTTPException default): {"detail": "error message"}
    Format 2 (Custom error handler): {"error": {"message": "error message", ...}}

    This makes tests futureproof against error format changes.
    """
    if "detail" in data:
        return data["detail"]
    elif "error" in data and isinstance(data["error"], dict):
        return data["error"].get("message", str(data["error"]))
    elif "message" in data:
        return data["message"]
    return str(data)


@pytest.fixture
def auth_headers():
    """Get authentication headers for API requests."""
    # conftest.py handles auth bypassing
    return {}


@pytest.fixture(autouse=True)
def mock_predictive_engine(monkeypatch):
    """Auto-use fixture to mock the predictive evolution engine for all tests."""
    from src.core.learning.predictive_evolution import predictive_evolution_engine

    # Mock methods with AsyncMock for async functions
    monkeypatch.setattr(predictive_evolution_engine, "initialize", AsyncMock(return_value=True))
    monkeypatch.setattr(
        predictive_evolution_engine,
        "get_system_evolution_status",
        AsyncMock(return_value={"status": "operational", "predictions_made": 100}),
    )
    monkeypatch.setattr(
        predictive_evolution_engine,
        "collect_system_metrics",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        predictive_evolution_engine,
        "predict_system_performance",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        predictive_evolution_engine,
        "generate_optimization_plan",
        AsyncMock(return_value={"plan": "optimize"}),
    )

    # Add mock attributes
    predictive_evolution_engine.predictions = []
    predictive_evolution_engine.predictions_history = []
    predictive_evolution_engine.metrics_history = []

    return predictive_evolution_engine


class TestInitializePredictiveSystem:
    """Test suite for /initialize endpoint."""

    def test_initialize_success(self, client, mock_predictive_engine):
        """Test successful system initialization."""
        response = client.post("/api/v1/prediction/initialize")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "capabilities" in data
        assert "performance_prediction" in data["capabilities"]
        mock_predictive_engine.initialize.assert_called_once()

    def test_initialize_failure(self, client, mock_predictive_engine, monkeypatch):
        """Test initialization failure."""
        monkeypatch.setattr(mock_predictive_engine, "initialize", AsyncMock(return_value=False))

        response = client.post("/api/v1/prediction/initialize")

        assert response.status_code == 500
        error_msg = get_error_message(response.json())
        assert "Failed to initialize" in error_msg

    def test_initialize_exception(self, client, mock_predictive_engine, monkeypatch):
        """Test initialization exception handling."""
        monkeypatch.setattr(
            mock_predictive_engine,
            "initialize",
            AsyncMock(side_effect=Exception("Test error")),
        )

        response = client.post("/api/v1/prediction/initialize")

        assert response.status_code == 500
        error_msg = get_error_message(response.json())
        assert "Initialization error" in error_msg or "Test error" in error_msg


class TestGetPredictionSystemStatus:
    """Test suite for /status endpoint."""

    def test_get_status_success(self, client, mock_predictive_engine):
        """Test successful status retrieval."""
        response = client.get("/api/v1/prediction/status")

        assert response.status_code == 200
        data = response.json()
        assert data["system_status"] == "operational"
        assert "prediction_engine" in data
        assert data["version"] == "1.0.0"

    def test_get_status_exception(self, client, mock_predictive_engine, monkeypatch):
        """Test status retrieval exception."""
        monkeypatch.setattr(
            mock_predictive_engine,
            "get_system_evolution_status",
            AsyncMock(side_effect=Exception("Engine error")),
        )

        response = client.get("/api/v1/prediction/status")

        assert response.status_code == 500
        error_msg = get_error_message(response.json())
        assert "Status retrieval error" in error_msg or "Engine error" in error_msg


class TestCollectSystemMetrics:
    """Test suite for /collect-metrics endpoint."""

    def test_collect_metrics_success(self, client, mock_predictive_engine, monkeypatch):
        """Test successful metric collection."""
        monkeypatch.setattr(
            mock_predictive_engine,
            "collect_system_metrics",
            AsyncMock(return_value=[{"cpu": 50}, {"memory": 75}]),
        )

        response = client.post("/api/v1/prediction/collect-metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["metrics_collected"] == 2
        assert "timestamp" in data

    def test_collect_metrics_exception(self, client, mock_predictive_engine, monkeypatch):
        """Test metric collection exception."""
        monkeypatch.setattr(
            mock_predictive_engine,
            "collect_system_metrics",
            AsyncMock(side_effect=Exception("Collection failed")),
        )

        response = client.post("/api/v1/prediction/collect-metrics")

        assert response.status_code == 500


class TestGeneratePredictions:
    """Test suite for /predict endpoint."""

    def test_predict_default_params(self, client, mock_predictive_engine, monkeypatch):
        """Test prediction with default parameters."""
        mock_pred = MagicMock()
        mock_pred.prediction_id = 1
        mock_pred.prediction_type.value = "cpu_usage"
        mock_pred.confidence = 0.85
        mock_pred.predicted_value = 75
        mock_pred.time_horizon = 24
        mock_pred.reasoning = "Test reasoning"
        mock_pred.recommended_actions = []
        mock_pred.impact_assessment = {}

        monkeypatch.setattr(
            mock_predictive_engine,
            "predict_system_performance",
            AsyncMock(return_value=[mock_pred]),
        )

        response = client.post(
            "/api/v1/prediction/predict",
            json={"hours_ahead": 24, "include_optimization_plan": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert "predictions" in data
        assert "system_status" in data

    def test_predict_custom_params(self, client, mock_predictive_engine, monkeypatch):
        """Test prediction with custom parameters."""
        mock_pred = MagicMock()
        mock_pred.prediction_id = 1
        mock_pred.prediction_type.value = "memory"
        mock_pred.confidence = 0.90
        mock_pred.predicted_value = 80
        mock_pred.time_horizon = 48
        mock_pred.reasoning = "Test"
        mock_pred.recommended_actions = []
        mock_pred.impact_assessment = {}

        monkeypatch.setattr(
            mock_predictive_engine,
            "predict_system_performance",
            AsyncMock(return_value=[mock_pred]),
        )

        response = client.post(
            "/api/v1/prediction/predict",
            json={
                "hours_ahead": 48,
                "prediction_types": ["cpu", "memory"],
                "include_optimization_plan": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "predictions" in data


class TestGetRecentPredictions:
    """Test suite for /predictions/recent endpoint."""

    def test_get_recent_default_limit(self, client, mock_predictive_engine):
        """Test getting recent predictions with default limit."""
        response = client.get("/api/v1/prediction/predictions/recent")

        assert response.status_code == 200
        data = response.json()
        assert "predictions" in data
        assert "total_count" in data

    def test_get_recent_custom_limit(self, client, mock_predictive_engine):
        """Test getting recent predictions with custom limit."""
        response = client.get("/api/v1/prediction/predictions/recent?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert "returned_count" in data


class TestGetPredictionHistory:
    """Test suite for /metrics/history endpoint."""

    def test_get_history_default_hours(self, client, mock_predictive_engine):
        """Test getting metrics history with default hours."""
        response = client.get("/api/v1/prediction/metrics/history")

        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "count" in data

    def test_get_history_custom_hours(self, client, mock_predictive_engine):
        """Test getting metrics history with custom hours."""
        response = client.get("/api/v1/prediction/metrics/history?hours=14")

        assert response.status_code == 200
        data = response.json()
        assert data["time_range_hours"] == 14


class TestOptimizeSystemConfiguration:
    """Test suite for /optimize/execute endpoint."""

    def test_optimize_success(self, client, mock_predictive_engine):
        """Test successful system optimization."""
        response = client.post("/api/v1/prediction/optimize/execute")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "optimization_initiated"
        assert "plan_id" in data


class TestAnalyzeTrends:
    """Test suite for /analytics/trends endpoint."""

    def test_analyze_trends_success(self, client, mock_predictive_engine):
        """Test trend analysis with default period."""
        response = client.get("/api/v1/prediction/analytics/trends")

        assert response.status_code == 200


class TestPredictionHealth:
    """Test suite for /health endpoint."""

    def test_health_check_healthy(self, client, mock_predictive_engine):
        """Test successful health check with operational status."""
        response = client.get("/api/v1/prediction/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "prediction_engine" in data

    def test_health_check_exception(self, client, mock_predictive_engine, monkeypatch):
        """Test health check exception handling."""
        monkeypatch.setattr(
            mock_predictive_engine,
            "get_system_evolution_status",
            AsyncMock(side_effect=Exception("Engine failed")),
        )

        response = client.get("/api/v1/prediction/health")

        # Health endpoint returns 200 with "unhealthy" status
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
