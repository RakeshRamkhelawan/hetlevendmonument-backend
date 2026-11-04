"""
Health Check Utilities - SanskritiSetu.org
Production-grade health checks for all critical dependencies

Task 5.3.2: Health Check Endpoints
- Database connectivity
- Redis connectivity (optional)
- LLM API connectivity
- Overall system readiness
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enum for consistency"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component"""

    name: str
    status: HealthStatus
    response_time_ms: float
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    last_check: datetime = field(default_factory=datetime.now)


@dataclass
class SystemHealth:
    """Overall system health aggregation"""

    status: HealthStatus
    components: dict[str, ComponentHealth]
    uptime_seconds: float
    version: str
    environment: str
    total_checks: int
    failed_checks: int
    degraded_checks: int
    timestamp: datetime = field(default_factory=datetime.now)


class HealthChecker:
    """
    Production-grade health checker with real dependency checks
    Supports liveness and readiness probes for Kubernetes
    """

    def __init__(self) -> None:
        self.startup_time = time.time()
        self.version = "1.0.0"
        self.environment = "production"
        self._last_health: SystemHealth | None = None
        self._check_timeout = 5.0  # seconds per check

    async def check_database(self) -> ComponentHealth:
        """
        Check database connectivity with actual query
        """
        start_time = time.time()
        try:
            from src.core.database.database import db_manager

            async with db_manager.get_session(max_retries=1) as session:
                from sqlalchemy import text

                result = await session.execute(text("SELECT 1"))
                _ = result.scalar()

            response_time = (time.time() - start_time) * 1000

            # Determine status based on response time
            if response_time < 100:
                status = HealthStatus.HEALTHY
            elif response_time < 500:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="database",
                status=status,
                response_time_ms=response_time,
                message="Database connection successful",
                details={"driver": "postgresql+asyncpg"},
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.CRITICAL,
                response_time_ms=response_time,
                message="Database connection failed",
                details={"error": "unavailable"},
            )

    async def check_redis(self) -> ComponentHealth:
        """
        Check Redis connectivity (optional - returns healthy if not configured)
        """
        start_time = time.time()
        try:
            from src.core.typing import create_async_redis_client

            from src.core.config.unified_config import config

            redis_url = config.get("REDIS_URL", "redis://localhost:6379")
            client = await create_async_redis_client(redis_url, decode_responses=True)

            try:
                await asyncio.wait_for(client.ping(), timeout=2.0)
                response_time = (time.time() - start_time) * 1000

                # Get Redis info
                info = await asyncio.wait_for(client.info("server"), timeout=2.0)
                redis_version = info.get("redis_version", "unknown")

                await client.close()

                if response_time < 50:
                    status = HealthStatus.HEALTHY
                elif response_time < 200:
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.UNHEALTHY

                return ComponentHealth(
                    name="redis",
                    status=status,
                    response_time_ms=response_time,
                    message="Redis connection successful",
                    details={"version": redis_version},
                )

            finally:
                await client.close()

        except ImportError:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNKNOWN,
                response_time_ms=0,
                message="Redis client not installed (optional)",
                details={"configured": False},
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.warning(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time,
                message="Redis not available",
                details={"error": "unavailable", "optional": True},
            )

    async def check_llm_api(self) -> ComponentHealth:
        """
        Check LLM API connectivity (OpenAI/Azure OpenAI)
        """
        start_time = time.time()
        try:
            import httpx

            from src.core.config.unified_config import config

            # Check if OpenAI is configured
            openai_key = config.get("OPENAI_API_KEY", "")
            azure_endpoint = config.get("AZURE_OPENAI_ENDPOINT", "")

            if not openai_key and not azure_endpoint:
                return ComponentHealth(
                    name="llm_api",
                    status=HealthStatus.UNKNOWN,
                    response_time_ms=0,
                    message="No LLM API configured",
                    details={"configured": False},
                )

            # Try to ping the API (lightweight check)
            async with httpx.AsyncClient(timeout=3.0) as client:
                if azure_endpoint:
                    # Azure OpenAI health check
                    response = await client.get(
                        f"{azure_endpoint}/openai/deployments?api-version=2024-02-15-preview",
                        headers={"api-key": config.get("AZURE_OPENAI_KEY", "")},
                    )
                else:
                    # OpenAI health check (models endpoint)
                    response = await client.get(
                        "https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {openai_key}"},
                    )

                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    status = HealthStatus.HEALTHY if response_time < 1000 else HealthStatus.DEGRADED
                    message = "LLM API connection successful"
                elif response.status_code == 401:
                    status = HealthStatus.UNHEALTHY
                    message = "LLM API authentication failed"
                else:
                    status = HealthStatus.DEGRADED
                    message = f"LLM API returned status {response.status_code}"

                return ComponentHealth(
                    name="llm_api",
                    status=status,
                    response_time_ms=response_time,
                    message=message,
                    details={
                        "provider": "azure" if azure_endpoint else "openai",
                        "status_code": response.status_code,
                    },
                )

        except Exception as e:
            response_time = max((time.time() - start_time) * 1000, 0)
            logger.warning(f"LLM API health check failed: {e}")
            return ComponentHealth(
                name="llm_api",
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time,
                message="LLM API check failed",
                details={"error": "unavailable"},
            )

    async def check_monitoring(self) -> ComponentHealth:
        """
        Check internal monitoring system
        """
        start_time = time.time()
        try:
            from src.core.monitoring.advanced_analytics import get_metrics_collector

            collector = get_metrics_collector()
            metrics = await collector.collect_system_metrics()

            response_time = (time.time() - start_time) * 1000

            return ComponentHealth(
                name="monitoring",
                status=HealthStatus.HEALTHY,
                response_time_ms=response_time,
                message="Monitoring system operational",
                details={"metrics_count": len(metrics)},
            )

        except Exception as e:
            logger.warning("Monitoring health check failed: %s: %s", type(e).__name__, e)
            response_time = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="monitoring",
                status=HealthStatus.DEGRADED,
                response_time_ms=response_time,
                message="Monitoring degraded",
                details={"error": "unavailable"},
            )

    async def check_focus_builder(self) -> ComponentHealth:
        """
        Check FocusBuilder subsystem health including:
        - Flows table existence
        - ActivePieces connectivity
        - Pieces cache freshness
        """
        start_time = time.time()
        checks_passed = 0
        total_checks = 3
        details: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        try:
            # Check 1: Database - flows table exists
            try:
                from sqlalchemy import text

                from src.core.database.database import db_manager

                async with db_manager.get_session(max_retries=1) as session:
                    result = await session.execute(text("SELECT COUNT(*) FROM flows"))
                    flow_count = result.scalar()
                    details["flows_count"] = flow_count
                    checks_passed += 1
            except Exception as e:
                logger.warning("Flows table check failed: %s: %s", type(e).__name__, e)
                details["flows_error"] = "unavailable"

            # Check 2: ActivePieces connectivity
            try:
                import httpx

                from src.core.config.unified_config import config

                ap_url = config.get("ACTIVEPIECES_API_URL", "http://activepieces:80/api/v1")
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(f"{ap_url.rstrip('/')}/health")
                    if response.status_code == 200:
                        details["activepieces"] = "connected"
                        checks_passed += 1
                    else:
                        details["activepieces"] = f"status_{response.status_code}"
            except Exception as e:
                if "RequestError" in type(e).__name__:
                    details["activepieces"] = "unreachable"
                else:
                    logger.warning("ActivePieces check failed: %s: %s", type(e).__name__, e)
                    details["activepieces_error"] = "unavailable"

            # Check 3: Pieces cache freshness
            try:
                from sqlalchemy import text

                from src.core.database.database import db_manager

                async with db_manager.get_session(max_retries=1) as session:
                    result = await session.execute(
                        text("SELECT COUNT(*) FROM focus_builder_pieces_cache")
                    )
                    pieces_count = result.scalar() or 0
                    details["pieces_cached"] = pieces_count
                    if pieces_count > 0:
                        checks_passed += 1
            except Exception as e:
                logger.warning("Pieces cache check failed: %s: %s", type(e).__name__, e)
                details["pieces_cache_error"] = "unavailable"

            response_time = (time.time() - start_time) * 1000

            # Determine status based on checks passed
            if checks_passed == total_checks:
                status = HealthStatus.HEALTHY
                message = "FocusBuilder fully operational"
            elif checks_passed >= 1:
                status = HealthStatus.DEGRADED
                message = f"FocusBuilder degraded ({checks_passed}/{total_checks} checks passed)"
            else:
                status = HealthStatus.UNHEALTHY
                message = "FocusBuilder unhealthy"

            return ComponentHealth(
                name="focus_builder",
                status=status,
                response_time_ms=response_time,
                message=message,
                details=details,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"FocusBuilder health check failed: {e}")
            return ComponentHealth(
                name="focus_builder",
                status=HealthStatus.CRITICAL,
                response_time_ms=response_time,
                message="FocusBuilder check failed",
                details={"error": "unavailable"},
            )

    async def liveness_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Kubernetes liveness probe - checks if the app is running
        Should be fast and not check external dependencies
        """
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.time() - self.startup_time,
        }

    async def readiness_check(self) -> SystemHealth:
        """
        Kubernetes readiness probe - checks if the app can serve traffic
        Checks all critical dependencies
        """
        # Run health checks in parallel with timeout
        checks = await asyncio.gather(
            asyncio.wait_for(self.check_database(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_redis(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_monitoring(), timeout=self._check_timeout),
            return_exceptions=True,
        )

        components: dict[str, ComponentHealth] = {}
        failed_checks = 0
        degraded_checks = 0

        check_names = ["database", "redis", "monitoring"]
        for i, check_result in enumerate(checks):
            name = check_names[i]

            if isinstance(check_result, BaseException):
                components[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.CRITICAL,
                    response_time_ms=self._check_timeout * 1000,
                    message=f"Check timeout/error: {str(check_result)[:50]}",
                )
                failed_checks += 1
            else:
                health_result: ComponentHealth = check_result
                components[name] = health_result
                if health_result.status == HealthStatus.CRITICAL:
                    failed_checks += 1
                elif health_result.status in (
                    HealthStatus.DEGRADED,
                    HealthStatus.UNHEALTHY,
                ):
                    degraded_checks += 1

        # Determine overall status
        # Critical if database is down, degraded for other issues
        db_health = components.get("database")
        if db_health and db_health.status == HealthStatus.CRITICAL:
            overall_status = HealthStatus.CRITICAL
        elif failed_checks > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_checks > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        health = SystemHealth(
            status=overall_status,
            components=components,
            uptime_seconds=time.time() - self.startup_time,
            version=self.version,
            environment=self.environment,
            total_checks=len(checks),
            failed_checks=failed_checks,
            degraded_checks=degraded_checks,
        )

        self._last_health = health
        return health

    async def full_health_check(self) -> SystemHealth:
        """
        Complete health check including LLM API (for /health endpoint)
        """
        # Run all health checks in parallel
        checks = await asyncio.gather(
            asyncio.wait_for(self.check_database(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_redis(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_llm_api(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_monitoring(), timeout=self._check_timeout),
            asyncio.wait_for(self.check_focus_builder(), timeout=self._check_timeout),
            return_exceptions=True,
        )

        components: dict[str, ComponentHealth] = {}
        failed_checks = 0
        degraded_checks = 0

        check_names = ["database", "redis", "llm_api", "monitoring", "focus_builder"]

        for i, check_result in enumerate(checks):
            name = check_names[i]

            if isinstance(check_result, BaseException):
                components[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.CRITICAL,
                    response_time_ms=self._check_timeout * 1000,
                    message=f"Check timeout/error: {str(check_result)[:50]}",
                )
                failed_checks += 1
            else:
                health_result: ComponentHealth = check_result
                components[name] = health_result
                if health_result.status == HealthStatus.CRITICAL:
                    failed_checks += 1
                elif health_result.status in (
                    HealthStatus.DEGRADED,
                    HealthStatus.UNHEALTHY,
                ):
                    degraded_checks += 1

        # Determine overall status
        db_health = components.get("database")
        if db_health and db_health.status == HealthStatus.CRITICAL:
            overall_status = HealthStatus.CRITICAL
        elif failed_checks > 1:  # More than 1 critical failure
            overall_status = HealthStatus.CRITICAL
        elif failed_checks > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_checks > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        health = SystemHealth(
            status=overall_status,
            components=components,
            uptime_seconds=time.time() - self.startup_time,
            version=self.version,
            environment=self.environment,
            total_checks=len(checks),
            failed_checks=failed_checks,
            degraded_checks=degraded_checks,
        )

        self._last_health = health
        return health

    def get_last_health(self) -> SystemHealth | None:
        """Get cached last health check result"""
        return self._last_health


# Global singleton instance
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Get or create the global health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
