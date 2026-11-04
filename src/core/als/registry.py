"""In-memory registry for per-tenant HealthMonitorService instances."""

from __future__ import annotations

from src.core.als.health_monitor import HealthMonitorService


class InMemoryHealthMonitorRegistry:
    """Dict-based lookup of HealthMonitorService per tenant."""

    def __init__(self) -> None:
        self._services: dict[int, HealthMonitorService] = {}

    def get_for_tenant(self, tenant_id: int) -> HealthMonitorService | None:
        """Return the HealthMonitorService for a tenant, or None."""
        return self._services.get(tenant_id)

    def register(self, tenant_id: int, service: HealthMonitorService) -> None:
        """Register a service for a tenant."""
        self._services[tenant_id] = service
