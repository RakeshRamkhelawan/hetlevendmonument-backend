"""
Unit tests for performance_analytics_endpoints.py - P4.2 Performance Analytics API
Tests 11 endpoints: dashboard, metrics, anomalies, trends, forecast, health score,
monitoring control (start/stop), status, history, recommendations.
"""

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mock auth_endpoints BEFORE importing target module
mock_auth_endpoints = MagicMock()
mock_auth_endpoints.get_current_user = AsyncMock()
sys.modules["src.core.api.auth_endpoints"] = mock_auth_endpoints
sys.modules["src.core.api.auth_endpoints"] = mock_auth_endpoints

from src.core.api.performance_analytics_endpoints import (
    get_analytics_dashboard,
    get_analytics_status,
    get_current_metrics,
    get_metrics_history,
    get_performance_anomalies,
    get_performance_forecast,
    get_performance_health_score,
    get_performance_recommendations,
    get_performance_trends,
    router,
    start_analytics_monitoring,
    stop_analytics_monitoring,
)

# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_permission():
    """Mock permission check."""
    return 1


@pytest.fixture
def mock_performance_analytics():
    """Mock performance_analytics module with all methods."""
    with patch("src.core.api.performance_analytics_endpoints.performance_analytics") as mock:
        # Dashboard
        mock.get_analytics_dashboard_data = AsyncMock()

        # Metrics
        mock.collect_performance_metrics = AsyncMock()

        # Anomalies
        mock.detect_performance_anomalies = AsyncMock(return_value=[])
        mock.anomalies = []

        # Trends
        mock.analyze_performance_trends = AsyncMock()

        # Forecast
        mock.get_performance_forecast = AsyncMock()

        # Health Score
        mock._calculate_performance_health_score = AsyncMock()

        # Monitoring Control
        mock.start_analytics_monitoring = AsyncMock()
        mock.stop_analytics_monitoring = AsyncMock()
        mock.analysis_interval = 60  # seconds

        # Status
        mock.get_analytics_status = AsyncMock()

        # Metrics History
        mock.metrics_history = []

        yield mock


# ============================================================
# TEST CLASS 1: DASHBOARD
# ============================================================


class TestGetAnalyticsDashboard:
    """Test GET /analytics/dashboard - Complete analytics dashboard data."""

    @pytest.mark.asyncio
    async def test_get_dashboard_success(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test successful dashboard data retrieval."""
        dashboard_data = {
            "current_metrics": {"cpu": 45.2, "memory": 68.5},
            "anomalies": [],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_analytics_dashboard(mock_user, mock_permission)

        assert result["success"] is True
        assert result["data"] == dashboard_data
        assert result["endpoint"] == "performance_analytics_dashboard"  # Actual endpoint name
        assert "timestamp" in result
        mock_performance_analytics.get_analytics_dashboard_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_dashboard_error(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test dashboard error handling."""
        mock_performance_analytics.get_analytics_dashboard_data.side_effect = Exception(
            "Dashboard error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_analytics_dashboard(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert str(exc_info.value.detail) == "Analytics dashboard error"


# ============================================================
# TEST CLASS 2: METRICS
# ============================================================


class TestGetCurrentMetrics:
    """Test GET /analytics/metrics - Real-time performance metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_success(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test successful metrics collection."""
        metrics = {"cpu_usage": 45.2, "memory_usage": 68.5, "api_response_time": 150}
        mock_performance_analytics.collect_performance_metrics.return_value = metrics

        result = await get_current_metrics(mock_user, mock_permission)

        assert result["success"] is True
        assert result["metrics"] == metrics
        assert result["collection_method"] == "real_time"
        assert "timestamp" in result
        mock_performance_analytics.collect_performance_metrics.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_metrics_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test metrics collection error."""
        mock_performance_analytics.collect_performance_metrics.side_effect = Exception(
            "Metrics error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_metrics(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Metrics collection error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 3: ANOMALIES
# ============================================================


class TestGetPerformanceAnomalies:
    """Test GET /analytics/anomalies - Anomaly detection with filtering."""

    @pytest.mark.asyncio
    async def test_get_anomalies_default_hours(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test anomaly detection with default 24-hour filter."""
        # Create anomalies within and outside 24-hour window
        now = datetime.now(timezone.utc)
        recent_anomaly = MagicMock()
        recent_anomaly.timestamp = now - timedelta(hours=12)
        recent_anomaly.metric_name = "cpu_usage"
        recent_anomaly.actual_value = 95.0
        recent_anomaly.expected_value = 50.0
        recent_anomaly.deviation_percentage = 90.0
        recent_anomaly.severity = MagicMock(value="critical")
        recent_anomaly.description = "High CPU usage"

        old_anomaly = MagicMock()
        old_anomaly.timestamp = now - timedelta(hours=36)

        mock_performance_analytics.detect_performance_anomalies.return_value = [
            recent_anomaly
        ]  # 1 new anomaly (list not int!)
        mock_performance_analytics.anomalies = [recent_anomaly, old_anomaly]

        # Correct signature: hours_back comes BEFORE current_user
        result = await get_performance_anomalies(24, mock_user, mock_permission)

        assert result["success"] is True
        assert result["new_anomalies_detected"] == 1
        assert len(result["anomalies"]) == 1  # Only recent anomaly
        assert result["anomalies"][0]["metric_name"] == "cpu_usage"
        assert result["time_range_hours"] == 24
        mock_performance_analytics.detect_performance_anomalies.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_anomalies_custom_hours(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test anomaly detection with custom hour filter."""
        now = datetime.now(timezone.utc)
        recent_anomaly = MagicMock()
        recent_anomaly.timestamp = now - timedelta(hours=6)
        recent_anomaly.metric_name = "memory_usage"
        recent_anomaly.actual_value = 92.0
        recent_anomaly.expected_value = 70.0
        recent_anomaly.deviation_percentage = 31.4
        recent_anomaly.severity = MagicMock(value="high")
        recent_anomaly.description = "Memory spike"

        mock_performance_analytics.detect_performance_anomalies.return_value = [
            recent_anomaly
        ]  # 1 new anomaly (list not int!)
        mock_performance_analytics.anomalies = [recent_anomaly]

        # Correct signature: hours_back=12 comes BEFORE current_user
        result = await get_performance_anomalies(12, mock_user, mock_permission)

        assert result["success"] is True
        assert result["time_range_hours"] == 12
        assert len(result["anomalies"]) == 1

    @pytest.mark.asyncio
    async def test_get_anomalies_error(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test anomaly detection error."""
        mock_performance_analytics.detect_performance_anomalies.side_effect = Exception(
            "Detection error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_performance_anomalies(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Anomaly detection error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 4: TRENDS
# ============================================================


class TestGetPerformanceTrends:
    """Test GET /analytics/trends - Advanced trend analysis."""

    @pytest.mark.asyncio
    async def test_get_trends_success(self, mock_user, mock_permission, mock_performance_analytics):
        """Test successful trend analysis."""
        trend1 = MagicMock()
        trend1.direction = "improving"
        trend1.trend_strength = 0.75
        trend1.prediction_7day = 45.2
        trend1.confidence = 0.92
        trend1.last_updated = datetime.now(timezone.utc)

        trends_dict = {"cpu_usage": trend1}
        mock_performance_analytics.analyze_performance_trends.return_value = trends_dict

        result = await get_performance_trends(mock_user, mock_permission)

        assert result["success"] is True
        assert "cpu_usage" in result["trends"]
        assert result["trends"]["cpu_usage"]["direction"] == "improving"
        assert result["trends"]["cpu_usage"]["strength"] == 0.75
        assert result["metrics_analyzed"] == 1
        assert result["analysis_method"] == "statistical_regression"
        mock_performance_analytics.analyze_performance_trends.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_trends_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test trend analysis error."""
        mock_performance_analytics.analyze_performance_trends.side_effect = Exception("Trend error")

        with pytest.raises(HTTPException) as exc_info:
            await get_performance_trends(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Trend analysis error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 5: FORECAST
# ============================================================


class TestGetPerformanceForecast:
    """Test GET /analytics/forecast/{metric_name} - Performance forecasting."""

    @pytest.mark.asyncio
    async def test_forecast_default_days(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test forecast with default 7-day horizon."""
        forecast_data = {"predictions": [45.2, 46.1, 44.8]}
        mock_performance_analytics.get_performance_forecast.return_value = forecast_data

        # Correct signature: metric_name, days_ahead, current_user, permission
        result = await get_performance_forecast("cpu_usage", 7, mock_user, mock_permission)

        assert result["success"] is True
        assert result["forecast"] == forecast_data
        assert result["metric_name"] == "cpu_usage"
        assert result["forecast_days"] == 7
        mock_performance_analytics.get_performance_forecast.assert_awaited_once_with("cpu_usage", 7)

    @pytest.mark.asyncio
    async def test_forecast_custom_days(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test forecast with custom day horizon."""
        forecast_data = {"predictions": [68.5, 69.2]}
        mock_performance_analytics.get_performance_forecast.return_value = forecast_data

        # Correct signature: metric_name, days_ahead=14, current_user, permission
        result = await get_performance_forecast("memory_usage", 14, mock_user, mock_permission)

        assert result["success"] is True
        assert result["metric_name"] == "memory_usage"
        assert result["forecast_days"] == 14
        mock_performance_analytics.get_performance_forecast.assert_awaited_once_with(
            "memory_usage", 14
        )

    @pytest.mark.asyncio
    async def test_forecast_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test forecast error."""
        mock_performance_analytics.get_performance_forecast.side_effect = Exception(
            "Forecast error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_performance_forecast("cpu_usage", mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Performance forecast error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 6: HEALTH SCORE
# ============================================================


class TestGetPerformanceHealthScore:
    """Test GET /analytics/health-score - Performance health scoring."""

    @pytest.mark.asyncio
    async def test_health_score_success(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test successful health score calculation."""
        health_score = 87.5
        mock_performance_analytics._calculate_performance_health_score.return_value = health_score

        result = await get_performance_health_score(mock_user, mock_permission)

        assert result["success"] is True
        assert result["health_score"] == health_score
        assert result["scoring_method"] == "weighted_multi_factor"
        assert "timestamp" in result
        mock_performance_analytics._calculate_performance_health_score.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_score_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test health score calculation error."""
        mock_performance_analytics._calculate_performance_health_score.side_effect = Exception(
            "Score error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_performance_health_score(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Health score calculation error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 7: MONITORING CONTROL
# ============================================================


class TestStartPerformanceMonitoring:
    """Test POST /analytics/monitoring/start - Start monitoring (WRITE)."""

    @pytest.mark.asyncio
    async def test_start_monitoring_success(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test successful monitoring start."""
        mock_performance_analytics.analysis_interval = 60

        result = await start_analytics_monitoring(mock_user, mock_permission)

        assert result["success"] is True
        assert "started" in result["message"].lower()
        assert result["monitoring_interval"] == 60
        assert "timestamp" in result
        mock_performance_analytics.start_analytics_monitoring.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_monitoring_error(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test monitoring start error."""
        mock_performance_analytics.start_analytics_monitoring.side_effect = Exception("Start error")

        with pytest.raises(HTTPException) as exc_info:
            await start_analytics_monitoring(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Analytics monitoring start error" in str(exc_info.value.detail)


class TestStopPerformanceMonitoring:
    """Test POST /analytics/monitoring/stop - Stop monitoring (WRITE)."""

    @pytest.mark.asyncio
    async def test_stop_monitoring_success(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test successful monitoring stop."""
        result = await stop_analytics_monitoring(mock_user, mock_permission)

        assert result["success"] is True
        assert "stopped" in result["message"].lower()
        assert "timestamp" in result
        mock_performance_analytics.stop_analytics_monitoring.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_monitoring_error(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test monitoring stop error."""
        mock_performance_analytics.stop_analytics_monitoring.side_effect = Exception("Stop error")

        with pytest.raises(HTTPException) as exc_info:
            await stop_analytics_monitoring(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Analytics monitoring stop error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 8: STATUS
# ============================================================


class TestGetAnalyticsStatus:
    """Test GET /analytics/status - System status and statistics."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, mock_user, mock_permission, mock_performance_analytics):
        """Test successful status retrieval."""
        status_data = {
            "monitoring_active": True,
            "anomalies_detected": 3,
            "uptime_seconds": 3600,
        }
        # Source calls get_analytics_status() WITHOUT await - it's synchronous
        mock_performance_analytics.get_analytics_status = MagicMock(return_value=status_data)

        result = await get_analytics_status(mock_user, mock_permission)

        assert result["success"] is True
        assert result["status"] == status_data
        assert result["system_component"] == "performance_analytics"
        assert "timestamp" in result
        mock_performance_analytics.get_analytics_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_status_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test status retrieval error."""
        # Synchronous method that raises exception
        mock_performance_analytics.get_analytics_status = MagicMock(
            side_effect=Exception("Status error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_analytics_status(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Analytics status error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 9: METRICS HISTORY
# ============================================================


class TestGetMetricsHistory:
    """Test GET /analytics/metrics/history - Historical metrics with filtering."""

    @pytest.mark.asyncio
    async def test_history_default_hours(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test metrics history with default 24-hour filter."""
        now = datetime.now(timezone.utc)
        metric1 = MagicMock()
        metric1.timestamp = now - timedelta(hours=12)
        metric1.metric_name = "cpu_usage"
        metric1.value = 45.2
        metric1.threshold_low = 20.0
        metric1.threshold_high = 80.0
        metric1.unit = "percent"

        metric2 = MagicMock()
        metric2.timestamp = now - timedelta(hours=36)  # Outside 24h window

        mock_performance_analytics.metrics_history = [metric1, metric2]

        # Correct signature: metric_name, hours_back, current_user, permission
        result = await get_metrics_history(None, 24, mock_user, mock_permission)

        assert result["success"] is True
        assert len(result["metrics_history"]) == 1  # Only recent metric
        assert result["total_records"] == 1
        assert result["time_range_hours"] == 24
        assert result["filtered_metric"] is None

    @pytest.mark.asyncio
    async def test_history_metric_name_filter(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test metrics history with specific metric filter."""
        now = datetime.now(timezone.utc)
        cpu_metric = MagicMock()
        cpu_metric.timestamp = now - timedelta(hours=6)
        cpu_metric.metric_name = "cpu_usage"
        cpu_metric.value = 45.2
        cpu_metric.threshold_low = 20.0
        cpu_metric.threshold_high = 80.0
        cpu_metric.unit = "percent"

        memory_metric = MagicMock()
        memory_metric.timestamp = now - timedelta(hours=6)
        memory_metric.metric_name = "memory_usage"

        mock_performance_analytics.metrics_history = [cpu_metric, memory_metric]

        # Correct signature: metric_name="cpu_usage", hours_back=12
        result = await get_metrics_history("cpu_usage", 12, mock_user, mock_permission)

        assert result["success"] is True
        assert len(result["metrics_history"]) == 1
        assert result["metrics_history"][0]["metric_name"] == "cpu_usage"
        assert result["filtered_metric"] == "cpu_usage"
        assert result["time_range_hours"] == 12

    @pytest.mark.asyncio
    async def test_history_error(self, mock_user, mock_permission, mock_performance_analytics):
        """Test metrics history error."""
        mock_performance_analytics.metrics_history = None  # Cause error

        with pytest.raises(HTTPException) as exc_info:
            await get_metrics_history(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Metrics history error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 10: RECOMMENDATIONS
# ============================================================


class TestGetPerformanceRecommendations:
    """Test GET /analytics/recommendations - Intelligent optimization recommendations."""

    @pytest.mark.asyncio
    async def test_recommendations_high_cpu(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations for high CPU usage."""
        dashboard_data = {
            "current_metrics": {"metrics": {"cpu_usage": 88, "memory_usage": 65}},
            "anomalies": [],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        assert result["total_recommendations"] > 0
        # Should have CPU optimization recommendation
        cpu_rec = next((r for r in result["recommendations"] if "CPU" in r["category"]), None)
        assert cpu_rec is not None
        assert cpu_rec["priority"] == "high"
        # Source has "High CPU usage" (capital H) in description
        assert "cpu" in cpu_rec["description"].lower() or "CPU" in cpu_rec["description"]

    @pytest.mark.asyncio
    async def test_recommendations_critical_memory(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations for critical memory usage."""
        dashboard_data = {
            "current_metrics": {"metrics": {"cpu_usage": 50, "memory_usage": 92}},
            "anomalies": [],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        # Should have critical memory recommendation
        mem_rec = next((r for r in result["recommendations"] if "Memory" in r["category"]), None)
        assert mem_rec is not None
        assert mem_rec["priority"] == "critical"

    @pytest.mark.asyncio
    async def test_recommendations_slow_api(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations for slow API response times."""
        dashboard_data = {
            "current_metrics": {
                "metrics": {
                    "cpu_usage": 50,
                    "memory_usage": 65,
                    "api_response_times": {"avg_response_time_ms": 2500},
                }
            },
            "anomalies": [],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        # Should have API performance recommendation
        api_rec = next((r for r in result["recommendations"] if "API" in r["category"]), None)
        assert api_rec is not None
        assert api_rec["priority"] == "high"

    @pytest.mark.asyncio
    async def test_recommendations_critical_anomalies(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations for critical anomalies."""
        dashboard_data = {
            "current_metrics": {"metrics": {}},
            "anomalies": [
                {"severity": "critical", "description": "System instability"},
                {"severity": "high", "description": "Minor issue"},
            ],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        # Should have anomaly resolution recommendation
        anom_rec = next((r for r in result["recommendations"] if "Anomaly" in r["category"]), None)
        assert anom_rec is not None
        assert anom_rec["priority"] == "critical"
        assert "1 issues" in anom_rec["description"]

    @pytest.mark.asyncio
    async def test_recommendations_degrading_trends(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations for degrading trends."""
        dashboard_data = {
            "current_metrics": {"metrics": {}},
            "anomalies": [],
            "trends": {
                "cpu_usage": {"direction": "degrading"},
                "memory_usage": {"direction": "stable"},
                "api_latency": {"direction": "degrading"},
            },
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        # Should have trend optimization recommendation
        trend_rec = next((r for r in result["recommendations"] if "Trend" in r["category"]), None)
        assert trend_rec is not None
        assert trend_rec["priority"] == "medium"
        assert "cpu_usage" in trend_rec["description"].lower()

    @pytest.mark.asyncio
    async def test_recommendations_no_issues(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations when no issues detected."""
        dashboard_data = {
            "current_metrics": {
                "metrics": {
                    "cpu_usage": 45,
                    "memory_usage": 65,
                    "api_response_times": {"avg_response_time_ms": 150},
                }
            },
            "anomalies": [],
            "trends": {},
        }
        mock_performance_analytics.get_analytics_dashboard_data.return_value = dashboard_data

        result = await get_performance_recommendations(mock_user, mock_permission)

        assert result["success"] is True
        assert result["total_recommendations"] == 0  # No issues, no recommendations
        assert "current_metrics" in result["analysis_based_on"]

    @pytest.mark.asyncio
    async def test_recommendations_error(
        self, mock_user, mock_permission, mock_performance_analytics
    ):
        """Test recommendations error."""
        mock_performance_analytics.get_analytics_dashboard_data.side_effect = Exception(
            "Dashboard error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_performance_recommendations(mock_user, mock_permission)

        assert exc_info.value.status_code == 500
        assert "Performance recommendations error" in str(exc_info.value.detail)


# ============================================================
# TEST CLASS 11: ROUTER CONFIGURATION
# ============================================================


class TestRouterConfiguration:
    """Test router registration and configuration."""

    def test_router_exists(self):
        """Test router is properly configured."""
        assert router is not None
        assert hasattr(router, "routes")
