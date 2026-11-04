"""Shared protocols for proactive monitor dependencies."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from src.core.als.health_monitor import HealthMonitorService


class TenantRepo(Protocol):
    """Protocol for tenant repository lookups."""

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        """Return the primary admin user_id for a tenant."""
        ...

    async def get_platform_admin_tenant_id(self) -> int:
        """Return the platform admin tenant_id (for global signals)."""
        ...

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:
        """Return the tenant_id that owns the given user, or None if not found.

        Used by event-driven monitors to resolve tenant ownership from user_id
        instead of trusting a user-controlled payload field (CLAUDE.md sec 6.1).
        """
        ...

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:
        """Return the tenant_id that owns the given workflow, or None if not found.

        Used by event-driven monitors to resolve tenant ownership from workflow_id
        instead of trusting a user-controlled payload field (CLAUDE.md sec 6.1).
        """
        ...


class HealthMonitorRegistry(Protocol):
    """Looks up per-tenant HealthMonitorService."""

    def get_for_tenant(self, tenant_id: int) -> HealthMonitorService | None:
        """Return the HealthMonitorService for a tenant, or None."""
        ...


class PrometheusClient(Protocol):
    """Abstracts Prometheus metric reads for monitors."""

    async def list_workflows(self, tenant_id: int) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return workflows tracked for a tenant."""
        ...

    async def execution_count(self, workflow_id: str, tenant_id: int, since: str) -> int:
        """Return number of executions in the given window."""
        ...

    async def get_histogram_p95(
        self, metric_name: str, labels: dict[str, str], since: str
    ) -> float:
        """Return P95 value for a histogram metric."""
        ...

    async def get_counter_sum(self, metric_name: str, labels: dict[str, str], since: str) -> float:
        """Return sum of a counter metric over the given window."""
        ...

    async def get_counter_average(
        self, metric_name: str, labels: dict[str, str], window: str, bucket: str
    ) -> float:
        """Return daily average of a counter over the window."""
        ...


class EventBusProtocol(Protocol):
    """Abstract event bus for monitor subscriptions.

    Implemented by SimpleEventBus (in-process) today;
    replaceable with Redis Pub/Sub tomorrow without monitor changes.
    """

    def subscribe(self, event_type: str, handler: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register an async handler for an event type."""
        ...

    def unsubscribe(self, event_type: str, handler: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Remove a handler."""
        ...

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Publish an event to all subscribers."""
        ...


class RoleRepo(Protocol):
    """Protocol for role repository lookups used by AuditAnomalyMonitor."""

    async def was_any_role_created_after(self, tenant_id: int, after: datetime) -> bool:
        """Return True if any role was created after the given timestamp for this tenant.

        Used to implement the 24h grace period: a spike in permission-denied
        events right after a role creation is likely a misconfiguration during
        rollout, not a security anomaly.
        """
        ...


class WorkflowRepo(Protocol):
    """Protocol for workflow repository lookups used by SensitiveWorkflowMonitor."""

    async def list_active(self, tenant_id: int) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return all active workflows for a tenant.

        Each item must expose .id and .config (or dict equivalents).
        """
        ...


class WorkflowPIIScanner(Protocol):
    """Protocol for scanning workflow configurations for PII field references.

    Decoupled from GDPREnforcer because GDPREnforcer enforces access control;
    this protocol scans config structure for PII field names.
    """

    def scan(self, config: Any) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Return list of PII field names found in the workflow config.

        Returns empty list when no PII fields are detected.
        """
        ...


class DPIARepo(Protocol):
    """Protocol for Data Protection Impact Assessment repository lookups."""

    async def exists_for_workflow(self, tenant_id: int, workflow_id: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Return True if a DPIA already exists for the given workflow.

        Used to skip SensitiveWorkflowMonitor signals for workflows that have
        already been reviewed.
        """
        ...
