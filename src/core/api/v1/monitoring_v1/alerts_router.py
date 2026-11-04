# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Monitoring alerts + profiler + system status endpoints.

Routes: GET /alerts, POST /trigger_alert, GET /alert/{alert_id},
        POST /profiler/start, POST /profiler/stop, GET /profiler/functions,
        DELETE /profiler/clear, GET /system/status,
        GET /mock-usage, GET /mock-usage/{component},
        POST /mock-usage/start-monitoring, POST /mock-usage/stop-monitoring,
        GET /mock-usage/thresholds
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from src.core.api.dependencies import require_admin_user
from pydantic import BaseModel

from src.core.api.v1.monitoring_v1.dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    require_scopes,
)
from src.core.monitoring.advanced_analytics import get_metrics_collector, get_profiler
from src.core.monitoring.mock_usage_detector import mock_usage_detector

logger = logging.getLogger(__name__)

# Startup time for uptime calculation
startup_time = time.time()

router = APIRouter()


class AlertsResponse(BaseModel):
    timestamp: datetime
    total_alerts: int
    critical_alerts: int
    warning_alerts: int
    info_alerts: int
    recent_alerts: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class MockUsageResponse(BaseModel):
    timestamp: datetime
    system_overview: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    components: dict[str, dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    recent_events: int
    monitoring_active: bool
    alert_thresholds: dict[str, float]


@router.get("/alerts", response_model=AlertsResponse)
async def get_system_alerts(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back for alerts"),
    severity: str | None = Query(
        None, pattern="^(critical|warning|info)$", description="Filter by severity"
    ),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> AlertsResponse:
    """Get system alerts. Requires: AGENTS_READ"""
    logger.info(
        "User %s requesting alerts (hours=%d, severity=%s)", current_user.id, hours, severity
    )
    metrics_collector = get_metrics_collector()
    try:
        current_metrics = await metrics_collector.collect_all_metrics()
        metrics_collector.check_alert_rules(current_metrics)

        cutoff_time = time.time() - (hours * 3600)
        recent_alerts = [
            alert for alert in metrics_collector.alerts if alert.timestamp >= cutoff_time
        ]

        if severity:
            recent_alerts = [alert for alert in recent_alerts if alert.severity == severity]

        critical_count = sum(1 for alert in recent_alerts if alert.severity == "critical")
        warning_count = sum(1 for alert in recent_alerts if alert.severity == "warning")
        info_count = sum(1 for alert in recent_alerts if alert.severity == "info")

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
            for alert in recent_alerts[-50:]
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
        logger.error("Failed to get alerts: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/trigger_alert")
async def trigger_alert(
    alert_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Trigger a manual alert. Requires: AGENTS_READ"""
    logger.info("User %s triggering alert: %s", current_user.id, alert_data)
    metrics_collector = get_metrics_collector()
    try:
        alert_id = str(uuid.uuid4())
        alert_type = alert_data.get("alert_type", "manual")

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

        metrics_collector.alerts.append(new_alert)

        return {"alert_id": alert_id, "status": "created", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to trigger alert: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/alert/{alert_id}")
async def get_alert_detail(
    alert_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get specific alert details. Requires: AGENTS_READ"""
    logger.info("User %s requesting alert %s", current_user.id, alert_id)
    metrics_collector = get_metrics_collector()
    try:
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
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get alert: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/profiler/start")
async def start_profiler(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Start performance profiling. Requires: ADMIN_ALL"""
    logger.info("User %s starting profiler", current_user.id)
    profiler = get_profiler()
    try:
        profiler.start_profiling()
        return {"message": "Performance profiling started", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to start profiler: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/profiler/stop")
async def stop_profiler(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Stop performance profiling. Requires: ADMIN_ALL"""
    logger.info("User %s stopping profiler", current_user.id)
    profiler = get_profiler()
    try:
        profiler.stop_profiling()
        return {"message": "Performance profiling stopped", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to stop profiler: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


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
    """Get function performance profiles. Requires: AGENTS_READ"""
    logger.info("User %s requesting function profiles", current_user.id)
    profiler = get_profiler()
    try:
        profiles: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
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
        logger.error("Failed to get function profiles: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.delete("/profiler/clear")
async def clear_profiler_data(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Clear all profiler data. Requires: ADMIN_ALL"""
    logger.info("User %s clearing profiler data", current_user.id)
    profiler = get_profiler()
    try:
        profiler.clear_profiles()
        return {"message": "Profiler data cleared", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to clear profiler data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/system/status")
async def get_system_status(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive system status. Requires: AGENTS_READ"""
    metrics_collector = get_metrics_collector()
    profiler = get_profiler()
    try:
        system_metrics = await metrics_collector.collect_system_metrics()
        health_score = metrics_collector.calculate_health_score(system_metrics)
        profiler_active = profiler.is_profiling
        profiler_functions = len(profiler.profiles)
        total_alerts = len(metrics_collector.alerts)
        recent_alerts = [
            alert for alert in metrics_collector.alerts if time.time() - alert.timestamp < 3600
        ]

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
        logger.error("Failed to get system status: %s", e, exc_info=True)
        return {"timestamp": datetime.now(timezone.utc), "error": "Er is een fout opgetreden.", "system_status": "error"}


@router.get("/mock-usage", response_model=MockUsageResponse)
async def get_mock_usage_report(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MockUsageResponse:
    """Get comprehensive mock usage report. Requires: AGENTS_READ"""
    try:
        report = await mock_usage_detector.get_system_mock_usage_report()
        return MockUsageResponse(**report)
    except Exception as e:
        logger.error("Failed to get mock usage report: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/mock-usage/{component}")
async def get_component_mock_usage(
    component: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get mock usage status for specific component. Requires: AGENTS_READ"""
    try:
        status = await mock_usage_detector.get_component_status(component)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Component '{component}' not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get component mock usage: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/mock-usage/start-monitoring")
async def start_mock_usage_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Start mock usage monitoring. Requires: ADMIN_ALL"""
    logger.info("User %s starting mock usage monitoring", current_user.id)
    try:
        await mock_usage_detector.start_monitoring()
        return {"message": "Mock usage monitoring started", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to start mock usage monitoring: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/mock-usage/stop-monitoring")
async def stop_mock_usage_monitoring(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Stop mock usage monitoring. Requires: ADMIN_ALL"""
    logger.info("User %s stopping mock usage monitoring", current_user.id)
    try:
        await mock_usage_detector.stop_monitoring()
        return {"message": "Mock usage monitoring stopped", "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error("Failed to stop mock usage monitoring: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/mock-usage/thresholds")
async def get_mock_usage_thresholds(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current mock usage alert thresholds. Requires: AGENTS_READ"""
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
        logger.error("Failed to get mock usage thresholds: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e
