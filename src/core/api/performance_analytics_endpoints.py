# orphan:exempt reason: actief gebruikt door tests; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
P4.2 Performance Analytics API Endpoints - Week 4 Mockdata Transformation
RESTful API endpoints for advanced performance analytics and monitoring
"""
# orphan:exempt -- legacy shim, pre-migration flat endpoint

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user, require_scopes, OAuth2Scope
from src.core.monitoring.performance_analytics import performance_analytics

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Analytics Dashboard Data - Complete analytics dashboard data with metrics, trends, and anomalies
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting analytics dashboard")
        dashboard_data = await performance_analytics.get_analytics_dashboard_data()
        return {
            "success": True,
            "data": dashboard_data,
            "endpoint": "performance_analytics_dashboard",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Analytics dashboard endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Analytics dashboard error")


@router.get("/analytics/metrics")
async def get_current_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Current Performance Metrics - Real-time performance metrics collection
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting current metrics")
        metrics = await performance_analytics.collect_performance_metrics()
        return {
            "success": True,
            "metrics": metrics,
            "collection_method": "real_time",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Current metrics endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Metrics collection error")


@router.get("/analytics/anomalies")
async def get_performance_anomalies(
    hours_back: int = Query(24, description="Hours of anomaly history to retrieve"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Performance Anomaly Detection - Advanced anomaly detection results
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting anomalies (hours_back={hours_back})")
        # Trigger anomaly detection
        current_anomalies = await performance_analytics.detect_performance_anomalies()

        # Filter by time range
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        filtered_anomalies = [
            {
                "timestamp": a.timestamp.isoformat(),
                "metric_name": a.metric_name,
                "actual_value": a.actual_value,
                "expected_value": a.expected_value,
                "deviation_percentage": a.deviation_percentage,
                "severity": a.severity,
                "description": a.description,
            }
            for a in performance_analytics.anomalies
            if a.timestamp > cutoff_time
        ]

        return {
            "success": True,
            "anomalies": filtered_anomalies,
            "new_anomalies_detected": len(current_anomalies),
            "total_anomalies": len(filtered_anomalies),
            "time_range_hours": hours_back,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Anomaly detection endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Anomaly detection error")


@router.get("/analytics/trends")
async def get_performance_trends(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Performance Trend Analysis - Advanced trend analysis with predictions
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting performance trends")
        trends = await performance_analytics.analyze_performance_trends()

        # Format trends for API response
        trend_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for metric_name, trend in trends.items():
            trend_data[metric_name] = {
                "direction": trend.direction,
                "strength": trend.trend_strength,
                "prediction_7day": trend.prediction_7day,
                "confidence": trend.confidence,
                "last_updated": trend.last_updated.isoformat(),
            }

        return {
            "success": True,
            "trends": trend_data,
            "metrics_analyzed": len(trend_data),
            "analysis_method": "statistical_regression",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Trend analysis endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Trend analysis error")


@router.get("/analytics/forecast/{metric_name}")
async def get_performance_forecast(
    metric_name: str,
    days_ahead: int = Query(7, description="Number of days to forecast ahead"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Performance Forecasting - Performance forecasting based on historical trends
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(
            f"User {current_user.id} requesting forecast for {metric_name} ({days_ahead} days)"
        )
        forecast = await performance_analytics.get_performance_forecast(metric_name, days_ahead)

        return {
            "success": True,
            "forecast": forecast,
            "metric_name": metric_name,
            "forecast_days": days_ahead,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Performance forecast endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Performance forecast error")


@router.get("/analytics/health-score")
async def get_performance_health_score(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Performance Health Score - Comprehensive performance health scoring
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting health score")
        health_score = await performance_analytics._calculate_performance_health_score()

        return {
            "success": True,
            "health_score": health_score,
            "scoring_method": "weighted_multi_factor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Health score endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Health score calculation error")


@router.post("/analytics/monitoring/start")
async def start_analytics_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Start Analytics Monitoring - Start continuous performance analytics monitoring
    Requires: OAuth2Scope.AGENTS_WRITE
    """
    try:
        logger.info(f"User {current_user.id} starting analytics monitoring")
        await performance_analytics.start_analytics_monitoring()

        return {
            "success": True,
            "message": "Performance analytics monitoring started",
            "monitoring_interval": performance_analytics.analysis_interval,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Start analytics monitoring failed: {e}")
        raise HTTPException(status_code=500, detail="Analytics monitoring start error")


@router.post("/analytics/monitoring/stop")
async def stop_analytics_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Stop Analytics Monitoring - Stop continuous performance analytics monitoring
    Requires: OAuth2Scope.AGENTS_WRITE
    """
    try:
        logger.info(f"User {current_user.id} stopping analytics monitoring")
        await performance_analytics.stop_analytics_monitoring()

        return {
            "success": True,
            "message": "Performance analytics monitoring stopped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Stop analytics monitoring failed: {e}")
        raise HTTPException(status_code=500, detail="Analytics monitoring stop error")


@router.get("/analytics/status")
async def get_analytics_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Analytics System Status - Analytics system status and statistics
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting analytics status")
        status = performance_analytics.get_analytics_status()

        return {
            "success": True,
            "status": status,
            "system_component": "performance_analytics",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Analytics status endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Analytics status error")


@router.get("/analytics/metrics/history")
async def get_metrics_history(
    metric_name: str | None = Query(None, description="Specific metric name to filter"),
    hours_back: int = Query(24, description="Hours of history to retrieve"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Metrics History - Historical metrics data for trend visualization
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(
            f"User {current_user.id} requesting metrics history (metric={metric_name}, hours={hours_back})"
        )
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        # Filter metrics history
        filtered_metrics: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for metric in performance_analytics.metrics_history:
            if metric.timestamp > cutoff_time:
                if metric_name is None or metric.metric_name == metric_name:
                    filtered_metrics.append(
                        {
                            "timestamp": metric.timestamp.isoformat(),
                            "metric_name": metric.metric_name,
                            "value": metric.value,
                            "threshold_low": metric.threshold_low,
                            "threshold_high": metric.threshold_high,
                            "unit": metric.unit,
                        }
                    )

        return {
            "success": True,
            "metrics_history": filtered_metrics,
            "total_records": len(filtered_metrics),
            "time_range_hours": hours_back,
            "filtered_metric": metric_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Metrics history endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Metrics history error")


@router.get("/analytics/recommendations")
async def get_performance_recommendations(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    P4.2 Performance Recommendations - Intelligent performance optimization recommendations
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting performance recommendations")
        # Get current analytics data
        dashboard_data = await performance_analytics.get_analytics_dashboard_data()

        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Analyze current metrics for recommendations
        current_metrics = dashboard_data.get("current_metrics", {}).get("metrics", {})

        # CPU usage recommendations
        cpu_usage = current_metrics.get("cpu_usage", 0)
        if cpu_usage > 85:
            recommendations.append(
                {
                    "category": "CPU Optimization",
                    "priority": "high",
                    "description": "High CPU usage detected - consider process optimization",
                    "impact": "Improve system responsiveness",
                    "implementation_effort": "Medium",
                    "expected_improvement": "15-25% CPU reduction",
                }
            )
        elif cpu_usage > 70:
            recommendations.append(
                {
                    "category": "CPU Monitoring",
                    "priority": "medium",
                    "description": "Elevated CPU usage - monitor for trends",
                    "impact": "Prevent future performance issues",
                    "implementation_effort": "Low",
                    "expected_improvement": "Proactive performance management",
                }
            )

        # Memory usage recommendations
        memory_usage = current_metrics.get("memory_usage", 0)
        if memory_usage > 90:
            recommendations.append(
                {
                    "category": "Memory Optimization",
                    "priority": "critical",
                    "description": "Critical memory usage - immediate optimization needed",
                    "impact": "Prevent system instability",
                    "implementation_effort": "High",
                    "expected_improvement": "20-30% memory reduction",
                }
            )

        # API performance recommendations
        api_metrics = current_metrics.get("api_response_times", {})
        if isinstance(api_metrics, dict):
            avg_response_time = api_metrics.get("avg_response_time_ms", 0)
            if avg_response_time > 2000:
                recommendations.append(
                    {
                        "category": "API Performance",
                        "priority": "high",
                        "description": "Slow API response times detected",
                        "impact": "Improve user experience",
                        "implementation_effort": "Medium",
                        "expected_improvement": "40-60% response time reduction",
                    }
                )

        # Anomaly-based recommendations
        anomalies = dashboard_data.get("anomalies", [])
        critical_anomalies = [a for a in anomalies if a.get("severity") == "critical"]
        if critical_anomalies:
            recommendations.append(
                {
                    "category": "Anomaly Resolution",
                    "priority": "critical",
                    "description": f"Critical performance anomalies detected ({len(critical_anomalies)} issues)",
                    "impact": "System stability and reliability",
                    "implementation_effort": "High",
                    "expected_improvement": "Resolve system instabilities",
                }
            )

        # Trend-based recommendations
        trends = dashboard_data.get("trends", {})
        degrading_trends = [
            name for name, trend in trends.items() if trend.get("direction") == "degrading"
        ]
        if degrading_trends:
            recommendations.append(
                {
                    "category": "Trend Optimization",
                    "priority": "medium",
                    "description": f"Degrading performance trends detected in: {', '.join(degrading_trends)}",
                    "impact": "Prevent future performance degradation",
                    "implementation_effort": "Medium",
                    "expected_improvement": "Stabilize performance trends",
                }
            )

        return {
            "success": True,
            "recommendations": recommendations,
            "total_recommendations": len(recommendations),
            "analysis_based_on": ["current_metrics", "anomalies", "trends"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Performance recommendations endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Performance recommendations error")
