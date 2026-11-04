"""ConsentExpiryMonitor - detects consent expiring within 7 days."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class ConsentRepo(Protocol):
    """Protocol for consent repository lookups."""

    async def list_users_with_expiring_consent(
        self, tenant_id: int, days_before_expiry: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return users whose consent expires within N days."""
        ...


class ConsentExpiryMonitor(ProactiveMonitor):
    """Detects users whose cross-session memory consent expires soon."""

    name = "consent_expiry"
    version = "1.0.0"
    interval_seconds = 86400  # 1x per day
    # Draait door bij een noodstop: een wettelijke termijn voor toestemming (AVG) loopt door, en
    # een signaal erover mag niet verdwijnen. De Council weigert wat eruit voortkomt.
    blijft_draaien_bij_noodstop = True
    default_severity = Severity.LOW  # ADR-027 Section 8.2: consent expiry = LOW

    DAYS_BEFORE_EXPIRY = 7

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
        consent_repo: ConsentRepo,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_repo = tenant_repo
        self._redis = redis
        self._consent_repo = consent_repo

    async def detect(self, tenant_id: int) -> list[Signal]:
        users = await self._consent_repo.list_users_with_expiring_consent(
            tenant_id, self.DAYS_BEFORE_EXPIRY
        )
        if not users:
            return []

        try:
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        except Exception as exc:
            logger.error(
                "consent_expiry: failed to get admin user id: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return []

        signals: list[Signal] = []
        for user in users:
            user_id = str(user.get("user_id", ""))
            if not user_id:
                logger.warning(
                    "consent_expiry: skipping user with missing user_id",
                    extra={"tenant_id": tenant_id, "monitor": self.name},
                )
                continue
            if await self._is_duplicate(tenant_id, user_id):
                continue
            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"Consent van gebruiker {user_id} verloopt over {self.DAYS_BEFORE_EXPIRY} dagen",
                    body=(
                        f"De cross-session memory consent van gebruiker '{user_id}' "
                        f"verloopt binnenkort. Vernieuwing aanbevolen."
                    ),
                    severity=Severity.LOW,
                    data_classification=DataClassification.RESTRICTED,
                    suggested_actions=[
                        {
                            "label": "Bekijk consent status",
                            "action": "navigate_to",
                            "params": {"route": f"/admin/users/{user_id}/consent"},
                        },
                        {
                            "label": "Stuur herinnering",
                            "action": "send_reminder",
                            "params": {"user_id": user_id, "type": "consent_expiry"},
                        },
                    ],
                    detection_reasoning=(f"Consent expires within {self.DAYS_BEFORE_EXPIRY} days"),
                    confidence=0.95,
                    context={
                        "user_id": user_id,
                        "days_before_expiry": self.DAYS_BEFORE_EXPIRY,
                    },
                )
            )

        logger.info(
            "consent_expiry detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
            },
        )

        async with best_effort("consent_expiry metrics"):
            pass

        return signals

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
