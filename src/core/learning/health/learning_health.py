"""
Health checks for Learning and Feedback services.

Provides:
- Database connectivity check
- Redis connectivity check
- Worker queue depth monitoring
- Overall health status
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class _RedisClient(Protocol):
    async def ping(self) -> object: ...

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: HealthStatus
    message: str
    latency_ms: float | None = None
    details: dict[str, object] | None = None


@dataclass
class LearningHealthReport:
    """Overall health report for learning services."""

    status: HealthStatus
    components: list[ComponentHealth]
    timestamp: str


class LearningHealthChecker:
    """
    Health checker for learning services.

    Usage:
        checker = LearningHealthChecker(db_session, redis_client)
        report = await checker.check_health()
    """

    def __init__(
        self, db_session: AsyncSession, redis_client: _RedisClient | None = None
    ) -> None:
        self._db = db_session
        self._redis = redis_client

    async def check_health(self) -> LearningHealthReport:
        """Perform comprehensive health check."""
        from datetime import datetime, timezone

        components: list[ComponentHealth] = []
        db_health = await self._check_database()
        components.append(db_health)

        if self._redis:
            redis_health = await self._check_redis()
            components.append(redis_health)

        status = self._determine_overall_status(components)

        return LearningHealthReport(
            status=status,
            components=components,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def _check_database(self) -> ComponentHealth:
        """Check database connectivity."""
        import time

        start = time.time()
        try:
            await self._db.execute(text("SELECT 1"))
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error("Database health check failed: %s: %s", type(e).__name__, e, exc_info=True)
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {e}",
                latency_ms=round(latency, 2),
            )

    async def _check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        import time

        if not self._redis:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis not configured (optional)",
                latency_ms=0,
            )

        start = time.time()
        try:
            await self._redis.ping()
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection OK",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error("Redis health check failed: %s: %s", type(e).__name__, e, exc_info=True)
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message=f"Redis connection failed: {e}",
                latency_ms=round(latency, 2),
            )

    def _determine_overall_status(self, components: list[ComponentHealth]) -> HealthStatus:
        """Determine overall health status from components."""
        statuses = [c.status for c in components]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def to_dict(
        self, report: LearningHealthReport
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert health report to dictionary."""
        return {
            "status": report.status.value,
            "timestamp": report.timestamp,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details,
                }
                for c in report.components
            ],
        }


async def check_learning_health(
    db_session: AsyncSession,
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Quick health check for learning services."""
    checker = LearningHealthChecker(db_session, redis_client)
    report = await checker.check_health()
    return checker.to_dict(report)
