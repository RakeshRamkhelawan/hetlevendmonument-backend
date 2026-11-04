# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/monitoring_v1/ (SP-API-003 Dag 4)
# Re-export composite router for any existing references.
from src.core.api.v1.monitoring_v1.router import router  # noqa: F401

"""
Monitoring API Endpoints - Sanskriti Setu
Advanced monitoring and metrics endpoints for production
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)
from src.core.monitoring.advanced_analytics import (
    LogAnalysisResult,
    get_log_analyzer,
    get_metrics_collector,
    get_monitoring_system,
    get_profiler,
)
from src.core.monitoring.mock_usage_detector import mock_usage_detector

logger = logging.getLogger(__name__)

# Initialize monitoring components
monitoring_system = get_monitoring_system()
metrics_collector = get_metrics_collector()
profiler = get_profiler()
log_analyzer = get_log_analyzer()


# Pydantic models for API responses
class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    uptime_seconds: float
    version: str = "1.0.0"
    environment: str = "production"
    components: dict[str, str]


class MetricsResponse(BaseModel):
    timestamp: datetime
    system_metrics: dict[str, float]
    application_metrics: dict[str, float]
    database_metrics: dict[str, float]
    health_score: float


class PerformanceResponse(BaseModel):
    timestamp: datetime
    analysis_period_minutes: int
    total_functions_profiled: int
    top_bottlenecks: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    performance_trends: dict[str, str]
    system_impact: dict[str, float]
    recommendations: list[str]
    alerts: list[str]


class LogAnalysisResponse(BaseModel):
    timestamp: datetime
    total_entries: int
    time_range: dict[str, str]
    error_rate: float
    warning_rate: float
    top_errors: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    anomalies: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    patterns: dict[str, int]
    insights: list[str]


class AlertsResponse(BaseModel):
    timestamp: datetime
    total_alerts: int
    critical_alerts: int
    warning_alerts: int
    info_alerts: int
    recent_alerts: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class ReadinessResponse(BaseModel):
    """Response model for readiness check"""

    status: str
    uptime_seconds: float
    version: str
    environment: str
    total_checks: int
    failed_checks: int
    degraded_checks: int
    components: dict[str, dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime


class LivenessResponse(BaseModel):
    """Response model for liveness check"""

    status: str
    uptime_seconds: float
    timestamp: datetime


# Create router
router = APIRouter(prefix="/monitoring", tags=["monitoring"])  # noqa: F811

# Startup time for uptime calculation
startup_time = time.time()

# =============================================================================
# KUBERNETES HEALTH PROBES (No authentication required)
# =============================================================================


@router.get("/live", response_model=LivenessResponse, tags=["health"])
async def liveness_probe() -> LivenessResponse:
    """
    Kubernetes Liveness Probe - Check if the application is alive

    No authentication required - used by load balancers and orchestrators.
    This is a lightweight check that only verifies the process is running.

    Returns:
        200: Application is alive

    Usage:
        livenessProbe:
          httpGet:
            path: /monitoring/live
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
    """
    from src.core.monitoring.health_checks import get_health_checker

    checker = get_health_checker()
    result = await checker.liveness_check()

    return LivenessResponse(
        status=result["status"],
        uptime_seconds=result["uptime_seconds"],
        timestamp=datetime.fromisoformat(result["timestamp"]),
    )


@router.get("/ready", response_model=ReadinessResponse, tags=["health"])
async def readiness_probe() -> ReadinessResponse | JSONResponse:
    """
    Kubernetes Readiness Probe - Check if the application can serve traffic

    No authentication required - used by load balancers to determine if
    traffic should be routed to this instance.

    Checks:
        - Database connectivity
        - Redis connectivity (optional)
        - Monitoring system

    Returns:
        200: Ready to serve traffic
        503: Not ready (dependencies unavailable)

    Usage:
        readinessProbe:
          httpGet:
            path: /monitoring/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
    """
    from src.core.monitoring.health_checks import HealthStatus, get_health_checker

    checker = get_health_checker()
    health = await checker.readiness_check()

    # Convert components to serializable format
    components_dict: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for name, component in health.components.items():
        components_dict[name] = {
            "status": component.status.value,
            "response_time_ms": component.response_time_ms,
            "message": component.message,
            "details": component.details,
        }

    response_data = ReadinessResponse(
        status=health.status.value,
        uptime_seconds=health.uptime_seconds,
        version=health.version,
        environment=health.environment,
        total_checks=health.total_checks,
        failed_checks=health.failed_checks,
        degraded_checks=health.degraded_checks,
        components=components_dict,
        timestamp=health.timestamp,
    )

    # Return 503 if not ready
    if health.status in (HealthStatus.CRITICAL, HealthStatus.UNHEALTHY):
        return JSONResponse(status_code=503, content=response_data.model_dump(mode="json"))

    return response_data


# =============================================================================
# AUTHENTICATED HEALTH ENDPOINTS
# =============================================================================


@router.get("/health", response_model=None)
async def get_health_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any] | JSONResponse:  # TODO(TYPE): replace Any with concrete type
    """
    Get system health status. Requires: AGENTS_READ
    Required by: test_production_security_headers, test_production_deployment_health
    """
    logger.info(f"User {current_user.id} checking system health")
    try:
        # Collect current metrics
        current_metrics = await metrics_collector.collect_all_metrics()
        health_score = metrics_collector.calculate_health_score(current_metrics)

        # Check component health
        components = {
            "api": "healthy" if health_score > 50 else "degraded",
            "database": "healthy",  # This would check actual DB connection
            "redis": "healthy",  # This would check actual Redis connection
            "ml_systems": "healthy" if health_score > 70 else "degraded",
            "monitoring": "healthy",
        }

        # Determine overall status
        if health_score >= 90:
            status = "healthy"
        elif health_score >= 70:
            status = "degraded"
        elif health_score >= 50:
            status = "unhealthy"
        else:
            status = "critical"

        # Create response data
        response_data = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.time() - startup_time,
            "version": "1.0.0",
            "environment": "production",
            "components": components,
        }

        # Create JSONResponse with security headers (required by test_production_security_headers)
        response = JSONResponse(status_code=200, content=response_data)

        # Add security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        response_data = {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.time() - startup_time,
            "version": "1.0.0",
            "environment": "production",
            "components": {"error": "Er is een fout opgetreden."},
        }

        response = JSONResponse(status_code=200, content=response_data)

        # Add security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response


@router.get("/metrics", response_model=MetricsResponse)
async def get_system_metrics(
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MetricsResponse:
    """
    Get comprehensive system metrics. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting system metrics")
    try:
        # Collect all metrics
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()

        # Calculate health score
        all_metrics = {**system_metrics, **app_metrics, **db_metrics}
        health_score = metrics_collector.calculate_health_score(all_metrics)

        # Store metrics in background
        background_tasks.add_task(metrics_collector.store_metrics, all_metrics)

        return MetricsResponse(
            timestamp=datetime.now(timezone.utc),
            system_metrics=system_metrics,
            application_metrics=app_metrics,
            database_metrics=db_metrics,
            health_score=health_score,
        )

    except Exception as e:
        logger.error(f"Failed to collect metrics: {e}")
        raise HTTPException(status_code=500, detail="Metrics collection failed")


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics_unauthenticated() -> str:
    """
    Get metrics in Prometheus format (unauthenticated).
    This endpoint is scraped by Prometheus and must NOT require authentication
    to allow monitoring infrastructure to function without service account credentials.
    """
    try:
        # Collect metrics
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()

        # Format as Prometheus metrics
        prometheus_output: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # System metrics
        for key, value in system_metrics.items():
            metric_name = f"sanskriti_system_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Application metrics
        for key, value in app_metrics.items():
            metric_name = f"sanskriti_app_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Database metrics
        for key, value in db_metrics.items():
            metric_name = f"sanskriti_db_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Health score
        health_score = metrics_collector.calculate_health_score(
            {**system_metrics, **app_metrics, **db_metrics}
        )
        prometheus_output.append("# TYPE sanskriti_health_score gauge")
        prometheus_output.append(f"sanskriti_health_score {health_score}")

        return "\n".join(prometheus_output)

    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return "# Error generating metrics"


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> str:
    """
    Get metrics in Prometheus format. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting Prometheus metrics")
    try:
        # Collect metrics
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()

        # Format as Prometheus metrics
        prometheus_output: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # System metrics
        for key, value in system_metrics.items():
            metric_name = f"sanskriti_system_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Application metrics
        for key, value in app_metrics.items():
            metric_name = f"sanskriti_app_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Database metrics
        for key, value in db_metrics.items():
            metric_name = f"sanskriti_db_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        # Health score
        health_score = metrics_collector.calculate_health_score(
            {**system_metrics, **app_metrics, **db_metrics}
        )
        prometheus_output.append("# TYPE sanskriti_health_score gauge")
        prometheus_output.append(f"sanskriti_health_score {health_score}")

        return "\n".join(prometheus_output)

    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return "# Error generating metrics"


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance_analysis(
    period_minutes: int = Query(60, ge=1, le=1440, description="Analysis period in minutes"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> PerformanceResponse:
    """
    Get comprehensive performance analysis. Requires: AGENTS_READ
    """
    logger.info(
        f"User {current_user.id} requesting performance analysis for {period_minutes} minutes"
    )
    try:
        # Generate performance report
        report = profiler.get_performance_report(period_minutes)

        # Format bottlenecks for response
        top_bottlenecks = [
            {
                "function_name": name,
                "bottleneck_score": score,
                "profile": (
                    {
                        "total_calls": profiler.profiles[name].total_calls,
                        "avg_time": profiler.profiles[name].avg_time,
                        "trend": profiler.profiles[name].trend,
                    }
                    if name in profiler.profiles
                    else {}
                ),
            }
            for name, score in report.top_bottlenecks
        ]

        return PerformanceResponse(
            timestamp=report.timestamp,
            analysis_period_minutes=period_minutes,
            total_functions_profiled=report.total_functions_profiled,
            top_bottlenecks=top_bottlenecks,
            performance_trends=report.performance_trends,
            system_impact=report.system_impact,
            recommendations=report.optimization_recommendations,
            alerts=report.alerts,
        )

    except Exception as e:
        logger.error(f"Failed to generate performance analysis: {e}")
        raise HTTPException(status_code=500, detail="Performance analysis failed")


@router.get("/logs/analysis", response_model=LogAnalysisResponse)
async def get_log_analysis(
    file_path: str | None = Query(None, description="Specific log file to analyze"),
    max_lines: int = Query(1000, ge=100, le=50000, description="Maximum lines to analyze"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> LogAnalysisResponse:
    """
    Get log analysis results. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting log analysis")
    try:
        # For demo purposes, we'll analyze a default log file or create mock data
        if file_path:
            analysis = await log_analyzer.analyze_log_file(file_path, max_lines)
        else:
            # Create mock log analysis for demonstration
            analysis = LogAnalysisResult(
                total_entries=1500,
                time_range=(
                    datetime.now(timezone.utc) - timedelta(hours=1),
                    datetime.now(timezone.utc),
                ),
                error_rate=2.3,
                warning_rate=8.7,
                top_errors=[
                    ("Database connection timeout", 15),
                    ("Authentication failed", 8),
                ],
                anomalies=[
                    {
                        "type": "rate_anomaly",
                        "description": "High error rate detected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                patterns={
                    "Database connection issues": 15,
                    "Authentication failures": 8,
                },
                insights=[
                    "Database connection pool may need tuning",
                    "Review authentication timeout settings",
                ],
            )

        # Format response
        return LogAnalysisResponse(
            timestamp=datetime.now(timezone.utc),
            total_entries=analysis.total_entries,
            time_range={
                "start": analysis.time_range[0].isoformat(),
                "end": analysis.time_range[1].isoformat(),
            },
            error_rate=analysis.error_rate,
            warning_rate=analysis.warning_rate,
            top_errors=[{"message": error[0], "count": error[1]} for error in analysis.top_errors],
            anomalies=analysis.anomalies,
            patterns=analysis.patterns,
            insights=analysis.insights,
        )

    except Exception as e:
        logger.error(f"Log analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Log analysis failed")


@router.get("/alerts", response_model=AlertsResponse)
async def get_system_alerts(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back for alerts"),
    severity: str | None = Query(
        None, pattern="^(critical|warning|info)$", description="Filter by severity"
    ),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> AlertsResponse:
    """
    Get system alerts. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting alerts (hours={hours}, severity={severity})")
    try:
        # Get current metrics to check for alerts
        current_metrics = await metrics_collector.collect_all_metrics()
        metrics_collector.check_alert_rules(current_metrics)

        # Filter recent alerts from metrics collector
        cutoff_time = time.time() - (hours * 3600)
        recent_alerts = [
            alert for alert in metrics_collector.alerts if alert.timestamp >= cutoff_time
        ]

        # Apply severity filter
        if severity:
            recent_alerts = [alert for alert in recent_alerts if alert.severity == severity]

        # Count by severity
        critical_count = sum(1 for alert in recent_alerts if alert.severity == "critical")
        warning_count = sum(1 for alert in recent_alerts if alert.severity == "warning")
        info_count = sum(1 for alert in recent_alerts if alert.severity == "info")

        # Format alerts for response
        formatted_alerts = [
            {
                "id": alert.id,
                "severity": alert.severity,
                "title": alert.title,
                "description": alert.description,
                "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat(),
                "resolved": alert.resolved,
                "metadata": alert.metadata,
            }
            for alert in recent_alerts[-50:]  # Last 50 alerts
        ]

        return AlertsResponse(
            timestamp=datetime.now(timezone.utc),
            total_alerts=len(recent_alerts),
            critical_alerts=critical_count,
            warning_alerts=warning_count,
            info_alerts=info_count,
            recent_alerts=formatted_alerts,
        )

    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(status_code=500, detail="Alert retrieval failed")


@router.post("/trigger_alert")
async def trigger_alert(
    alert_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Trigger a manual alert. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} triggering alert: {alert_data}")
    try:
        import uuid

        alert_id = str(uuid.uuid4())
        alert_type = alert_data.get("alert_type", "manual")

        # Create alert object
        from datetime import datetime, timezone
        from src.core.monitoring.advanced_analytics import SystemAlert

        new_alert = SystemAlert(
            id=alert_id,
            severity="info",
            title=f"Manual Alert: {alert_type}",
            description=f"Triggered by user {current_user.email}",
            timestamp=datetime.now(timezone.utc).timestamp(),
            resolved=False,
            metadata=alert_data,
        )

        # Add to metrics collector
        metrics_collector.alerts.append(new_alert)

        return {"alert_id": alert_id, "status": "created", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to trigger alert: {e}")
        raise HTTPException(status_code=500, detail="Alert trigger failed")


@router.get("/alert/{alert_id}")
async def get_alert_detail(
    alert_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get specific alert details. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting alert {alert_id}")
    try:
        # Search for alert in metrics collector
        for alert in metrics_collector.alerts:
            if alert.id == alert_id:
                return {
                    "id": alert.id,
                    "severity": alert.severity,
                    "title": alert.title,
                    "description": alert.description,
                    "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat(),
                    "resolved": alert.resolved,
                    "metadata": alert.metadata,
                }

        # Alert not found
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert: {e}")
        raise HTTPException(status_code=500, detail="Alert retrieval failed")


@router.post("/profiler/start")
async def start_profiler(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Start performance profiling. Requires: ADMIN_ALL
    """
    logger.info(f"User {current_user.id} starting profiler")
    try:
        profiler.start_profiling()
        return {"message": "Performance profiling started", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to start profiler: {e}")
        raise HTTPException(status_code=500, detail="Profiler start failed")


@router.post("/profiler/stop")
async def stop_profiler(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Stop performance profiling. Requires: ADMIN_ALL
    """
    logger.info(f"User {current_user.id} stopping profiler")
    try:
        profiler.stop_profiling()
        return {"message": "Performance profiling stopped", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to stop profiler: {e}")
        raise HTTPException(status_code=500, detail="Profiler stop failed")


@router.get("/profiler/functions")
async def get_function_profiles(
    limit: int = Query(20, ge=1, le=100, description="Number of functions to return"),
    sort_by: str = Query(
        "bottleneck_score",
        pattern="^(bottleneck_score|total_time|total_calls|avg_time)$",
    ),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get function performance profiles. Requires: AGENTS_READ
    """
    logger.info(f"User {current_user.id} requesting function profiles")
    try:
        # Get all function profiles
        profiles: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for name, profile in profiler.profiles.items():
            profiles.append(
                {
                    "name": name,
                    "total_calls": profile.total_calls,
                    "total_time": profile.total_time,
                    "avg_time": profile.avg_time,
                    "min_time": profile.min_time,
                    "max_time": profile.max_time,
                    "median_time": profile.median_time,
                    "std_time": profile.std_time,
                    "call_frequency": profile.call_frequency,
                    "trend": profile.trend,
                    "bottleneck_score": profile.bottleneck_score,
                }
            )

        # Sort profiles
        if sort_by == "bottleneck_score":
            profiles.sort(key=lambda x: x["bottleneck_score"], reverse=True)
        elif sort_by == "total_time":
            profiles.sort(key=lambda x: x["total_time"], reverse=True)
        elif sort_by == "total_calls":
            profiles.sort(key=lambda x: x["total_calls"], reverse=True)
        elif sort_by == "avg_time":
            profiles.sort(key=lambda x: x["avg_time"], reverse=True)

        return {
            "timestamp": datetime.now(timezone.utc),
            "total_functions": len(profiles),
            "sort_by": sort_by,
            "functions": profiles[:limit],
        }

    except Exception as e:
        logger.error(f"Failed to get function profiles: {e}")
        raise HTTPException(status_code=500, detail="Function profiles retrieval failed")


@router.delete("/profiler/clear")
async def clear_profiler_data(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Clear all profiler data. Requires: ADMIN_ALL
    """
    logger.info(f"User {current_user.id} clearing profiler data")
    try:
        profiler.clear_profiles()
        return {"message": "Profiler data cleared", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to clear profiler data: {e}")
        raise HTTPException(status_code=500, detail="Profiler clear failed")


@router.get("/system/status")
async def get_system_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get comprehensive system status. Requires: AGENTS_READ
    """
    try:
        # Collect basic system info
        system_metrics = await metrics_collector.collect_system_metrics()
        health_score = metrics_collector.calculate_health_score(system_metrics)

        # Get profiler status
        profiler_active = profiler.is_profiling
        profiler_functions = len(profiler.profiles)

        # Get alert counts
        total_alerts = len(metrics_collector.alerts)
        recent_alerts = [
            alert for alert in metrics_collector.alerts if time.time() - alert.timestamp < 3600
        ]  # Last hour

        return {
            "timestamp": datetime.now(timezone.utc),
            "uptime_seconds": time.time() - startup_time,
            "health_score": health_score,
            "system_status": (
                "healthy" if health_score > 80 else "degraded" if health_score > 50 else "critical"
            ),
            "monitoring": {
                "profiler_active": profiler_active,
                "functions_profiled": profiler_functions,
                "total_alerts": total_alerts,
                "recent_alerts": len(recent_alerts),
            },
            "system_metrics": {
                "cpu_usage": system_metrics.get("cpu_usage", 0),
                "memory_usage": system_metrics.get("memory_usage", 0),
                "disk_usage": system_metrics.get("disk_usage", 0),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {"timestamp": datetime.now(timezone.utc), "error": "Er is een fout opgetreden.", "system_status": "error"}


# Mock Usage Detection Endpoints (P1.4 Implementation)
class MockUsageResponse(BaseModel):
    timestamp: datetime
    system_overview: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    components: dict[str, dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    recent_events: int
    monitoring_active: bool
    alert_thresholds: dict[str, float]


@router.get("/mock-usage", response_model=MockUsageResponse)
async def get_mock_usage_report(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MockUsageResponse:
    """
    Get comprehensive mock usage report. Requires: AGENTS_READ
    """
    try:
        report = await mock_usage_detector.get_system_mock_usage_report()
        return MockUsageResponse(**report)
    except Exception as e:
        logger.error(f"Failed to get mock usage report: {e}")
        raise HTTPException(status_code=500, detail="Mock usage report failed")


@router.get("/mock-usage/{component}")
async def get_component_mock_usage(
    component: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get mock usage status for specific component. Requires: AGENTS_READ
    """
    try:
        status = await mock_usage_detector.get_component_status(component)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Component '{component}' not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get component mock usage: {e}")
        raise HTTPException(status_code=500, detail="Component mock usage query failed")


@router.post("/mock-usage/start-monitoring")
async def start_mock_usage_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Start mock usage monitoring. Requires: ADMIN_ALL
    """
    logger.info(f"User {current_user.id} starting mock usage monitoring")
    try:
        await mock_usage_detector.start_monitoring()
        return {"message": "Mock usage monitoring started", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to start mock usage monitoring: {e}")
        raise HTTPException(status_code=500, detail="Mock usage monitoring start failed")


@router.post("/mock-usage/stop-monitoring")
async def stop_mock_usage_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Stop mock usage monitoring. Requires: ADMIN_ALL
    """
    logger.info(f"User {current_user.id} stopping mock usage monitoring")
    try:
        await mock_usage_detector.stop_monitoring()
        return {"message": "Mock usage monitoring stopped", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Failed to stop mock usage monitoring: {e}")
        raise HTTPException(status_code=500, detail="Mock usage monitoring stop failed")


@router.get("/mock-usage/thresholds")
async def get_mock_usage_thresholds(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get current mock usage alert thresholds. Requires: AGENTS_READ
    """
    try:
        return {
            "timestamp": datetime.now(timezone.utc),
            "thresholds": {
                "low": mock_usage_detector.low_threshold,
                "medium": mock_usage_detector.medium_threshold,
                "high": mock_usage_detector.high_threshold,
                "critical": mock_usage_detector.critical_threshold,
            },
            "descriptions": {
                "low": f"Alert when mock usage >= {mock_usage_detector.low_threshold:.1%}",
                "medium": f"Alert when mock usage >= {mock_usage_detector.medium_threshold:.1%}",
                "high": f"Alert when mock usage >= {mock_usage_detector.high_threshold:.1%}",
                "critical": f"Alert when mock usage >= {mock_usage_detector.critical_threshold:.1%}",
            },
        }
    except Exception as e:
        logger.error(f"Failed to get mock usage thresholds: {e}")
        raise HTTPException(status_code=500, detail="Threshold query failed")
