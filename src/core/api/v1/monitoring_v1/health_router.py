# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Monitoring health probe endpoints (Kubernetes liveness + readiness + authenticated health).

Routes: GET /live, GET /ready, GET /health
"""

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.api.v1.monitoring_v1.dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    require_scopes,
)

# Startup time for uptime calculation
startup_time = time.time()

router = APIRouter()


class LivenessResponse(BaseModel):
    """Response model for liveness check"""

    status: str
    uptime_seconds: float
    timestamp: datetime


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


@router.get("/live", response_model=LivenessResponse, tags=["health"])
async def liveness_probe() -> LivenessResponse:
    """
    Kubernetes Liveness Probe - Check if the application is alive.
    No authentication required.
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
    Kubernetes Readiness Probe - Check if the application can serve traffic.
    No authentication required.
    """
    from src.core.monitoring.health_checks import HealthStatus, get_health_checker

    checker = get_health_checker()
    health = await checker.readiness_check()

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

    if health.status in (HealthStatus.CRITICAL, HealthStatus.UNHEALTHY):
        return JSONResponse(status_code=503, content=response_data.model_dump(mode="json"))

    return response_data


@router.get("/health", response_model=None)
async def get_health_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any] | JSONResponse:  # TODO(TYPE): replace Any with concrete type
    """Get system health status. Requires: AGENTS_READ"""
    import logging

    from src.core.monitoring.advanced_analytics import get_metrics_collector

    log = logging.getLogger(__name__)
    log.info("User %s checking system health", current_user.id)

    metrics_collector = get_metrics_collector()
    try:
        current_metrics = await metrics_collector.collect_all_metrics()
        health_score = metrics_collector.calculate_health_score(current_metrics)

        components = {
            "api": "healthy" if health_score > 50 else "degraded",
            "database": "healthy",
            "redis": "healthy",
            "ml_systems": "healthy" if health_score > 70 else "degraded",
            "monitoring": "healthy",
        }

        if health_score >= 90:
            status = "healthy"
        elif health_score >= 70:
            status = "degraded"
        elif health_score >= 50:
            status = "unhealthy"
        else:
            status = "critical"

        response_data = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.time() - startup_time,
            "version": "1.0.0",
            "environment": "production",
            "components": components,
        }

        response = JSONResponse(status_code=200, content=response_data)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

    except Exception as e:
        log.error("Health check failed: %s", e, exc_info=True)
        response_data = {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.time() - startup_time,
            "version": "1.0.0",
            "environment": "production",
            "components": {"error": "Er is een fout opgetreden."},
        }
        response = JSONResponse(status_code=200, content=response_data)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
