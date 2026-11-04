"""Stub repository implementations for ProactiveScheduler dependencies (SP-WE-21).

NOTE (technical debt): These stubs return empty/None results to allow the
ProactiveScheduler to start. Compliance monitors (ConsentExpiry, AuditAnomaly,
SensitiveWorkflow) will emit no signals until real repositories are wired.

Full implementations are tracked separately. Each stub satisfies the Protocol
defined in src/core/copilot/proactive/monitors/protocols.py (or in the monitor
module itself for repo-specific protocols).

Tenant isolation: stubs accept tenant_id but never return data across tenants
because they return empty results unconditionally. All invocations are logged
at DEBUG level for observability.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StubConsentRepo:
    """Stub for ConsentRepo Protocol. Returns no expiring consent records."""

    def __init__(self, session_factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session_factory = session_factory
        logger.debug("Initialized StubConsentRepo with session_factory")

    async def list_users_with_expiring_consent(
        self, tenant_id: int, days_before_expiry: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return empty list -- no expiring consent detected (stub)."""
        logger.debug(
            "StubConsentRepo.list_users_with_expiring_consent (tenant_id=%d, days_before_expiry=%d)",
            tenant_id,
            days_before_expiry,
        )
        return []


class StubAuditRepo:
    """Stub for AuditRepo Protocol. Returns no permission-denied events."""

    def __init__(self, session_factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session_factory = session_factory
        logger.debug("Initialized StubAuditRepo with session_factory")

    async def count_permission_denied_per_user(
        self, tenant_id: int, hours: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return empty list -- no anomalies detected (stub)."""
        logger.debug(
            "StubAuditRepo.count_permission_denied_per_user (tenant_id=%d, hours=%d)",
            tenant_id,
            hours,
        )
        return []


class StubRoleRepo:
    """Stub for RoleRepo Protocol. Reports no recent role creations (fail-safe)."""

    def __init__(self, session_factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session_factory = session_factory
        logger.debug("Initialized StubRoleRepo with session_factory")

    async def was_any_role_created_after(self, tenant_id: int, after: datetime) -> bool:
        """Return False -- no recent role creation (stub, fail-safe default).

        Returning False means the 24h grace period is NOT applied, so the
        AuditAnomalyMonitor will still emit signals if real anomalies arise.
        """
        logger.debug(
            "StubRoleRepo.was_any_role_created_after (tenant_id=%d, after=%s)",
            tenant_id,
            after.isoformat() if hasattr(after, "isoformat") else str(after),
        )
        return False


class StubWorkflowRepo:
    """Stub for WorkflowRepo Protocol. Returns no active workflows."""

    def __init__(self, session_factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session_factory = session_factory
        logger.debug("Initialized StubWorkflowRepo with session_factory")

    async def list_active(
        self, tenant_id: int
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return empty list -- no active workflows (stub)."""
        logger.debug("StubWorkflowRepo.list_active (tenant_id=%d)", tenant_id)
        return []


class StubDPIARepo:
    """Stub for DPIARepo Protocol. Reports no DPIA records exist."""

    def __init__(self, session_factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._session_factory = session_factory
        logger.debug("Initialized StubDPIARepo with session_factory")

    async def exists_for_workflow(
        self,
        tenant_id: int,
        workflow_id: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Return False -- no DPIA on file (stub).

        With WorkflowRepo also returning empty, no signal will be emitted.
        """
        logger.debug(
            "StubDPIARepo.exists_for_workflow (tenant_id=%d, workflow_id=%s)",
            tenant_id,
            workflow_id,
        )
        return False


class StubWorkflowPIIScanner:
    """Stub for WorkflowPIIScanner Protocol. Reports no PII detected."""

    def scan(self, config: Any) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Return empty list -- no PII fields detected (stub)."""
        logger.debug("StubWorkflowPIIScanner.scan called with config")
        return []


class StubPrometheusClient:
    """Stub for PrometheusClient Protocol. Reports no metrics.

    Real implementation should query an actual Prometheus instance. Until then
    WorkflowLatencyMonitor and TokenSpikeMonitor emit no signals.
    """

    async def list_workflows(
        self, tenant_id: int
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        logger.debug("StubPrometheusClient.list_workflows (tenant_id=%d)", tenant_id)
        return []

    async def execution_count(self, workflow_id: str, tenant_id: int, since: str) -> int:
        logger.debug(
            "StubPrometheusClient.execution_count (workflow_id=%s, tenant_id=%d, since=%s)",
            workflow_id,
            tenant_id,
            since,
        )
        return 0

    async def get_histogram_p95(
        self, metric_name: str, labels: dict[str, str], since: str
    ) -> float:
        logger.debug(
            "StubPrometheusClient.get_histogram_p95 (metric=%s, labels=%s, since=%s)",
            metric_name,
            labels,
            since,
        )
        return 0.0

    async def get_counter_sum(self, metric_name: str, labels: dict[str, str], since: str) -> float:
        logger.debug(
            "StubPrometheusClient.get_counter_sum (metric=%s, labels=%s, since=%s)",
            metric_name,
            labels,
            since,
        )
        return 0.0

    async def get_counter_average(
        self, metric_name: str, labels: dict[str, str], window: str, bucket: str
    ) -> float:
        logger.debug(
            "StubPrometheusClient.get_counter_average (metric=%s, labels=%s, window=%s, bucket=%s)",
            metric_name,
            labels,
            window,
            bucket,
        )
        return 0.0


__all__ = [
    "StubAuditRepo",
    "StubConsentRepo",
    "StubDPIARepo",
    "StubPrometheusClient",
    "StubRoleRepo",
    "StubWorkflowPIIScanner",
    "StubWorkflowRepo",
]
