"""AuditAnomalyMonitor -- detects permission-denied spikes per tenant."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import RoleRepo, TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class AuditRepo(Protocol):
    """Protocol for audit log repository lookups."""

    async def count_permission_denied_per_user(
        self, tenant_id: int, hours: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return list of {user_id, count} for permission-denied events."""
        ...


class AuditAnomalyMonitor(ProactiveMonitor):
    """Detects when 3+ users in a tenant get permission-denied in 24h.

    Includes a 24h grace period after any role creation to avoid false
    positives during RBAC rollout (ADR-027 valkuil: new roles legitimately
    generate permission-denied events before users receive the correct scopes).
    """

    name = "audit_anomaly"
    version = "1.1.0"
    interval_seconds = 3600  # 1x per hour
    # Draait door bij een noodstop: een beveiligingswaakhond op het auditlog mag niet blind worden
    # juist als een beheerder een klant heeft stilgezet. De Council weigert wat eruit voortkomt.
    blijft_draaien_bij_noodstop = True
    default_severity = Severity.HIGH

    UNIQUE_USERS_THRESHOLD = 3
    LOOKBACK_HOURS = 24
    GRACE_PERIOD_HOURS = 24  # skip if a role was created in the last 24h

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
        audit_repo: AuditRepo,
        role_repo: RoleRepo,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_repo = tenant_repo
        self._redis = redis
        self._audit_repo = audit_repo
        self._role_repo = role_repo

    async def detect(self, tenant_id: int) -> list[Signal]:
        user_counts = await self._audit_repo.count_permission_denied_per_user(
            tenant_id, self.LOOKBACK_HOURS
        )
        affected_users = [u for u in user_counts if u.get("count", 0) >= 3]
        if len(affected_users) < self.UNIQUE_USERS_THRESHOLD:
            return []

        # Grace period: a recent role creation can legitimately cause
        # permission-denied events during rollout. Skip to avoid false positives.
        grace_cutoff = datetime.now(timezone.utc) - timedelta(hours=self.GRACE_PERIOD_HOURS)
        try:
            if await self._role_repo.was_any_role_created_after(tenant_id, grace_cutoff):
                logger.info(
                    "audit_anomaly: skipping signal -- role created within grace period",
                    extra={"tenant_id": tenant_id, "monitor": self.name},
                )
                return []
        except Exception as exc:
            logger.error(
                "audit_anomaly: role_repo check failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            # Fail-open: if we cannot check grace period, still emit the signal
            # to avoid silent blind spots. Operator can review the role history.

        if await self._is_duplicate(tenant_id, "daily"):
            return []

        try:
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        except Exception as exc:
            logger.error(
                "audit_anomaly: failed to get admin user id: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return []
        total_denied = sum(u.get("count", 0) for u in affected_users)

        logger.info(
            "audit_anomaly detect: signal emitted",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "affected_users": len(affected_users),
                "total_denied": total_denied,
            },
        )

        async with best_effort("audit_anomaly metrics"):
            pass

        return [
            Signal(
                tenant_id=tenant_id,
                affected_user_id=admin_user_id,
                monitor_name=self.name,
                title=f"{len(affected_users)} gebruikers kregen toegang geweigerd",
                body=(
                    f"In de laatste {self.LOOKBACK_HOURS}u kregen "
                    f"{len(affected_users)} unieke gebruikers permission-denied "
                    f"({total_denied}x totaal). Mogelijk RBAC-probleem."
                ),
                severity=Severity.HIGH,
                data_classification=DataClassification.INTERNAL,
                suggested_actions=[
                    {
                        "label": "Bekijk audit log",
                        "action": "navigate_to",
                        "params": {"route": "/admin/audit"},
                    },
                    {
                        "label": "Bekijk RBAC config",
                        "action": "navigate_to",
                        "params": {"route": "/admin/rbac"},
                    },
                    {
                        "label": "Snooze 1u",
                        "action": "snooze_signal",
                        "params": {"duration_seconds": 3600},
                    },
                ],
                detection_reasoning=(
                    f"{len(affected_users)} users >= threshold "
                    f"{self.UNIQUE_USERS_THRESHOLD} with permission-denied "
                    f"in last {self.LOOKBACK_HOURS}h; no role created in last "
                    f"{self.GRACE_PERIOD_HOURS}h"
                ),
                confidence=0.90,
                context={
                    "affected_user_count": len(affected_users),
                    "total_denied": total_denied,
                    "threshold": self.UNIQUE_USERS_THRESHOLD,
                    "lookback_hours": self.LOOKBACK_HOURS,
                    "grace_period_hours": self.GRACE_PERIOD_HOURS,
                },
            )
        ]

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
