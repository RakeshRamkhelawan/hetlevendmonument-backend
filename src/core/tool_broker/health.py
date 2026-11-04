#!/usr/bin/env python3
"""
Health Check System for Tool Broker Service

Provides:
- Service health status monitoring
- Component health tracking
- Graceful degradation strategies
- Health-aware routing decisions

Integrates with circuit breaker patterns to provide comprehensive
health monitoring and automatic service recovery coordination.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from collections.abc import Callable

from loguru import logger

# ============================================================================
# HEALTH STATUS ENUMS
# ============================================================================


class HealthStatus(Enum):
    """Health status of a component"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(Enum):
    """Types of components in the Tool Broker system"""

    SERENA_CLIENT = "serena_client"
    SEQUENTIAL_THINKING_CLIENT = "sequential_thinking_client"
    DATABASE = "database"
    CACHE = "cache"
    EXTERNAL_SERVICE = "external_service"


# ============================================================================
# COMPONENT HEALTH
# ============================================================================


class ComponentHealth:
    """Tracks health of a single component"""

    def __init__(
        self,
        name: str,
        component_type: ComponentType,
        check_interval_seconds: int = 30,
        unhealthy_threshold: int = 3,
    ) -> None:
        self.name = name
        self.component_type = component_type
        self.check_interval_seconds = check_interval_seconds
        self.unhealthy_threshold = unhealthy_threshold

        self.status = HealthStatus.UNKNOWN
        self.last_check_time: datetime | None = None
        self.failure_count = 0
        self.success_count = 0
        self.last_error: str | None = None
        self.response_time_ms: float | None = None

    async def check_health(self, check_func: Callable[..., Any]) -> HealthStatus:  # TODO(TYPE): replace Any with concrete type
        """Execute health check"""
        try:
            start_time = datetime.now(timezone.utc)
            is_healthy = await check_func()
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            self.response_time_ms = response_time
            self.last_check_time = datetime.now(timezone.utc)

            if is_healthy:
                self.failure_count = 0
                self.success_count += 1
                self.status = HealthStatus.HEALTHY
                self.last_error = None
                logger.debug(
                    f"Component '{self.name}' health check: HEALTHY ({response_time:.2f}ms)"
                )
            else:
                self._on_failure("Health check returned false")

            return self.status

        except Exception as e:
            self._on_failure(str(e))
            return self.status

    def _on_failure(self, error: str) -> None:
        """Handle health check failure"""
        self.failure_count += 1
        self.last_error = error
        self.last_check_time = datetime.now(timezone.utc)

        if self.failure_count >= self.unhealthy_threshold:
            self.status = HealthStatus.UNHEALTHY
            logger.error(
                f"Component '{self.name}' marked UNHEALTHY after "
                f"{self.failure_count} failures: {error}"
            )
        else:
            self.status = HealthStatus.DEGRADED
            logger.warning(
                f"Component '{self.name}' health check failed "
                f"({self.failure_count}/{self.unhealthy_threshold}): {error}"
            )

    def is_healthy(self) -> bool:
        """Check if component is healthy"""
        return self.status == HealthStatus.HEALTHY

    def is_degraded(self) -> bool:
        """Check if component is degraded"""
        return self.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]

    def reset(self) -> None:
        """Reset component health status"""
        self.status = HealthStatus.UNKNOWN
        self.failure_count = 0
        self.success_count = 0
        self.last_error = None
        self.response_time_ms = None
        logger.info(f"Component '{self.name}' health status reset")

    def get_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get component health status"""
        return {
            "name": self.name,
            "type": self.component_type.value,
            "status": self.status.value,
            "last_check_time": self.last_check_time,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_error": self.last_error,
            "response_time_ms": self.response_time_ms,
        }


# ============================================================================
# SERVICE HEALTH
# ============================================================================


class ServiceHealth:
    """Tracks overall service health"""

    def __init__(self, service_name: str = "Tool Broker") -> None:
        self.service_name = service_name
        self.components: dict[str, ComponentHealth] = {}
        self.startup_time: datetime | None = None
        self.shutdown_time: datetime | None = None
        self.is_running = False

        logger.info(f"Service health tracker initialized for '{service_name}'")

    def register_component(
        self, name: str, component_type: ComponentType, check_interval_seconds: int = 30
    ) -> ComponentHealth:
        """Register a component to monitor"""
        component = ComponentHealth(name, component_type, check_interval_seconds)
        self.components[name] = component
        logger.info(f"Registered component: {name} ({component_type.value})")
        return component

    def get_component(self, name: str) -> ComponentHealth | None:
        """Get component by name"""
        return self.components.get(name)

    async def check_all_components(self) -> dict[str, HealthStatus]:
        """Check health of all registered components"""
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for name, component in self.components.items():
            # Check if it's time to check
            if component.last_check_time:
                time_since_check = datetime.now(timezone.utc) - component.last_check_time
                if time_since_check.total_seconds() < component.check_interval_seconds:
                    results[name] = component.status
                    continue

            # This is a placeholder - actual check would be provided by caller
            results[name] = component.status

        return results

    def get_overall_health(self) -> HealthStatus:
        """Get overall service health based on components"""
        if not self.components:
            return HealthStatus.UNKNOWN

        statuses = [c.status for c in self.components.values()]

        # If any component is unhealthy, service is degraded
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.DEGRADED

        # If all components are healthy
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY

        # If some components are degraded or unknown
        return HealthStatus.DEGRADED

    def get_healthy_components_count(self) -> int:
        """Get count of healthy components"""
        return sum(1 for c in self.components.values() if c.is_healthy())

    def get_degraded_components_count(self) -> int:
        """Get count of degraded/unhealthy components"""
        return sum(1 for c in self.components.values() if c.is_degraded())

    def mark_startup(self) -> None:
        """Mark service as started"""
        self.startup_time = datetime.now(timezone.utc)
        self.is_running = True
        logger.info(f"Service '{self.service_name}' marked as started")

    def mark_shutdown(self) -> None:
        """Mark service as shutdown"""
        self.shutdown_time = datetime.now(timezone.utc)
        self.is_running = False
        logger.info(f"Service '{self.service_name}' marked as shutdown")

    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds"""
        if not self.startup_time:
            return 0

        end_time = self.shutdown_time or datetime.now(timezone.utc)
        uptime = end_time - self.startup_time
        return uptime.total_seconds()

    def get_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive service health status"""
        return {
            "service_name": self.service_name,
            "overall_health": self.get_overall_health().value,
            "is_running": self.is_running,
            "startup_time": self.startup_time,
            "uptime_seconds": self.get_uptime_seconds(),
            "components_total": len(self.components),
            "components_healthy": self.get_healthy_components_count(),
            "components_degraded": self.get_degraded_components_count(),
            "components": [c.get_status() for c in self.components.values()],
        }


# ============================================================================
# HEALTH CHECK PROBES
# ============================================================================


class HealthCheckProbe:
    """Defines a health check probe"""

    def __init__(
        self,
        name: str,
        check_func: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        timeout_seconds: float = 5.0,
        critical: bool = False,
    ) -> None:
        self.name = name
        self.check_func = check_func
        self.timeout_seconds = timeout_seconds
        self.critical = critical

    async def execute(self) -> bool:
        """Execute the health check probe"""
        try:
            result = await asyncio.wait_for(self.check_func(), timeout=self.timeout_seconds)
            # Type narrowing: result from check_func() is checked to be bool
            probe_result: bool = bool(result)
            return probe_result
        except TimeoutError:
            logger.warning(f"Health check probe '{self.name}' timed out")
            return False
        except Exception as e:
            logger.error(f"Health check probe '{self.name}' failed: {e}")
            return False


# ============================================================================
# LIVENESS AND READINESS PROBES
# ============================================================================


class LivenessProbe:
    """Kubernetes-style liveness probe - checks if service is alive"""

    def __init__(self, service_health: ServiceHealth) -> None:
        self.service_health = service_health

    async def check(self) -> bool:
        """Check if service is alive"""
        # Service is alive if it's running
        if not self.service_health.is_running:
            return False

        # Service is alive if most components are not unhealthy
        unhealthy_count = self.service_health.get_degraded_components_count()
        total_count = len(self.service_health.components)

        # Allow up to 50% degradation before marking as dead
        return unhealthy_count < (total_count * 0.5)


class ReadinessProbe:
    """Kubernetes-style readiness probe - checks if service can accept traffic"""

    def __init__(self, service_health: ServiceHealth) -> None:
        self.service_health = service_health

    async def check(self) -> bool:
        """Check if service is ready to accept traffic"""
        # Service is ready if it's running and all critical components are healthy
        if not self.service_health.is_running:
            return False

        # Check if all components are at least healthy
        overall_health = self.service_health.get_overall_health()
        return overall_health in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]


# ============================================================================
# GRACEFUL DEGRADATION
# ============================================================================


class DegradationStrategy:
    """Strategy for handling degraded components"""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    async def execute(self, health: ServiceHealth) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute degradation strategy. Subclasses override for specific strategies."""
        logger.debug(
            "DegradationStrategy.execute called on base class for service=%s", health.service_name
        )
        return {}


class CircuitBreakerDegradation(DegradationStrategy):
    """Strategy: Disable circuit breaker to fail fast"""

    def __init__(self) -> None:
        super().__init__(
            "circuit_breaker_fallback",
            "Allow requests to fail immediately instead of queuing",
        )

    async def execute(self, health: ServiceHealth) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Open circuit breaker for failing components"""
        affected_components: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for component in health.components.values():
            if component.is_degraded():
                affected_components.append(component.name)

        logger.warning(
            f"Activating circuit breaker degradation for components: {affected_components}"
        )

        return {
            "strategy": self.name,
            "affected_components": affected_components,
            "action": "circuit_breaker_opened",
        }


class ReducedCapacityDegradation(DegradationStrategy):
    """Strategy: Reduce concurrent requests during degradation"""

    def __init__(self, capacity_reduction_percent: int = 50) -> None:
        super().__init__(
            "reduced_capacity",
            f"Reduce concurrent request capacity by {capacity_reduction_percent}%",
        )
        self.capacity_reduction_percent = capacity_reduction_percent

    async def execute(self, health: ServiceHealth) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Reduce concurrent request capacity"""
        degraded_count = health.get_degraded_components_count()

        if degraded_count > 0:
            logger.warning(
                f"Activating reduced capacity degradation: "
                f"reducing capacity by {self.capacity_reduction_percent}%"
            )

            return {
                "strategy": self.name,
                "degraded_components": degraded_count,
                "capacity_reduction_percent": self.capacity_reduction_percent,
                "action": "capacity_reduced",
            }

        return {"strategy": self.name, "action": "no_action_needed"}


# ============================================================================
# GLOBAL SERVICE HEALTH INSTANCE
# ============================================================================

_service_health: ServiceHealth | None = None


def get_service_health() -> ServiceHealth:
    """Get or create global service health instance"""
    global _service_health
    if _service_health is None:
        _service_health = ServiceHealth("Tool Broker Service")
    return _service_health


def initialize_service_health(
    service_name: str = "Tool Broker Service",
) -> ServiceHealth:
    """Initialize global service health instance"""
    global _service_health
    _service_health = ServiceHealth(service_name)
    return _service_health
