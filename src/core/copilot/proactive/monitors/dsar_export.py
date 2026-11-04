"""DSARExportMonitor - detects PII exports initiated by users."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import EventBusProtocol, TenantRepo
from src.core.copilot.proactive.types import Signal

logger = logging.getLogger(__name__)


class DSARExportMonitor(ProactiveMonitor):
    """Detects when a user initiates an export containing PII data."""

    name = "dsar_export"
    version = "1.0.0"
    interval_seconds = 0  # event-driven
    default_severity = Severity.HIGH

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
        event_bus: EventBusProtocol,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_repo = tenant_repo
        self._redis = redis
        self._event_bus = event_bus
        # Subscribe to export-initiated events on instantiation.
        # Handler is bound so we can call propose_to_council directly.
        self._event_bus.subscribe("dsar.export_initiated", self._on_export_initiated)

    async def detect(self, tenant_id: int) -> list[Signal]:
        """Event-driven monitors return empty; work happens via event handler."""
        return []

    async def _on_export_initiated(self, payload: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Handle export-initiated event: build Signal and propose to Council."""
        # tenant_id is intentionally NOT read from payload (CLAUDE.md sec 6.1 -- B-005).
        # It is resolved server-side from user_id via TenantRepo.
        user_id = payload.get("user_id")
        export_type = payload.get("export_type", "unknown")
        contains_pii = payload.get("contains_pii", False)

        if not isinstance(user_id, int):
            logger.warning(
                "dsar_export_monitor: invalid payload user_id=%r",
                user_id,
                extra={"monitor": self.name},
            )
            return

        # Resolve tenant ownership from user_id -- server-side, not spoofable.
        tenant_id = await self._tenant_repo.get_tenant_id_for_user(user_id)
        if tenant_id is None:
            logger.warning(
                "dsar_export_monitor: unknown user_id=%r -- no tenant found, rejecting event",
                user_id,
                extra={"monitor": self.name},
            )
            return

        if not isinstance(export_type, str) or len(export_type) > 64:
            logger.warning(
                "dsar_export_monitor: invalid export_type=%r",
                export_type,
                extra={"tenant_id": tenant_id},
            )
            return

        if contains_pii is not True:
            return  # only alert on PII exports

        # Per-event dedup (user + export_type) prevents duplicate alerts
        # for the same export if event is republished.
        dedup_key = f"{user_id}:{export_type}"
        if await self._is_duplicate(tenant_id, dedup_key):
            return

        try:
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        except Exception as exc:
            logger.error(
                "dsar_export_monitor: failed to get admin user id: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return
        signal = Signal(
            tenant_id=tenant_id,
            affected_user_id=admin_user_id,
            monitor_name=self.name,
            title=f"PII-export gestart door gebruiker {user_id}",
            body=(
                f"Gebruiker {user_id} heeft een {export_type}-export gestart "
                f"die persoonsgegevens bevat. Controle vereist per GDPR Art. 15."
            ),
            severity=Severity.HIGH,
            data_classification=DataClassification.CONFIDENTIAL,
            suggested_actions=[
                {
                    "label": "Bekijk export details",
                    "action": "navigate_to",
                    "params": {"route": f"/admin/dsar/exports/{user_id}"},
                },
                {
                    "label": "Review PII-kolommen",
                    "action": "review_pii_columns",
                    "params": {"export_type": export_type},
                },
                {
                    "label": "Bevestig export",
                    "action": "confirm_export",
                    "params": {"user_id": user_id, "export_type": export_type},
                },
            ],
            detection_reasoning=(
                f"DSAR export_initiated event for user {user_id} with contains_pii=True"
            ),
            confidence=1.0,
            context={
                "user_id": user_id,
                "export_type": export_type,
                "contains_pii": contains_pii,
            },
        )

        try:
            await self.propose_to_council(signal)
        except Exception as exc:
            logger.error(
                "dsar_export_monitor: propose_to_council failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        # TTL = 1 hour for event-driven dedup
        existed = await self._redis.set(key, "1", nx=True, ex=3600)
        return existed is None
