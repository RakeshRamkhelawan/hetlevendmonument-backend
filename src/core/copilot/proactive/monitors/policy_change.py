"""PolicyChangeMonitor - detects workflow configs containing PII fields."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import EventBusProtocol, TenantRepo
from src.core.copilot.proactive.types import Signal

logger = logging.getLogger(__name__)


class PolicyChangeMonitor(ProactiveMonitor):
    """Detects when a workflow config is updated to include PII fields."""

    name = "policy_change"
    version = "1.0.0"
    interval_seconds = 0  # event-driven
    default_severity = Severity.MEDIUM

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
        self._event_bus.subscribe("workflow.config_updated", self._on_config_updated)

    async def detect(self, tenant_id: int) -> list[Signal]:
        """Event-driven monitors return empty; work happens via event handler."""
        return []

    async def _on_config_updated(self, payload: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Handle workflow-config-updated event."""
        # tenant_id is intentionally NOT read from payload (CLAUDE.md sec 6.1 -- B-005).
        # It is resolved server-side from workflow_id via TenantRepo.
        workflow_id = payload.get("workflow_id")
        workflow_name = payload.get("workflow_name", "unknown")
        has_pii_fields = payload.get("has_pii_fields", False)

        if not workflow_id:
            logger.warning(
                "policy_change_monitor: invalid payload workflow_id=%r",
                workflow_id,
                extra={"monitor": self.name},
            )
            return

        if not isinstance(workflow_id, (str, int)) or not str(workflow_id):
            logger.warning(
                "policy_change_monitor: invalid workflow_id=%r",
                workflow_id,
                extra={"monitor": self.name},
            )
            return

        if not isinstance(workflow_name, str) or len(workflow_name) > 128:
            logger.warning(
                "policy_change_monitor: invalid workflow_name=%r",
                workflow_name,
                extra={"monitor": self.name},
            )
            return

        # Resolve tenant ownership from workflow_id -- server-side, not spoofable.
        tenant_id = await self._tenant_repo.get_tenant_id_for_workflow(workflow_id)
        if tenant_id is None:
            logger.warning(
                "policy_change_monitor: unknown workflow_id=%r -- no tenant found, rejecting event",
                workflow_id,
                extra={"monitor": self.name},
            )
            return

        if has_pii_fields is not True:
            return  # only alert when PII is involved

        dedup_key = f"{workflow_id}"
        if await self._is_duplicate(tenant_id, dedup_key):
            return

        try:
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        except Exception as exc:
            logger.error(
                "policy_change_monitor: failed to get admin user id: %s: %s",
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
            title=f"Workflow '{workflow_name}' bevat nu persoonsgegevens",
            body=(
                f"Workflow '{workflow_name}' (id={workflow_id}) is gewijzigd "
                f"en bevat nu PII-kolommen. DPIA-review aanbevolen."
            ),
            severity=Severity.MEDIUM,
            data_classification=DataClassification.CONFIDENTIAL,
            suggested_actions=[
                {
                    "label": "Bekijk workflow config",
                    "action": "navigate_to",
                    "params": {"route": f"/workflows/{workflow_id}"},
                },
                {
                    "label": "Open DPIA template",
                    "action": "open_dpia",
                    "params": {"workflow_id": workflow_id},
                },
            ],
            detection_reasoning=(
                f"workflow.config_updated event for {workflow_id} with has_pii_fields=True"
            ),
            confidence=1.0,
            context={
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "has_pii_fields": has_pii_fields,
            },
        )

        try:
            await self.propose_to_council(signal)
        except Exception as exc:
            logger.error(
                "policy_change_monitor: propose_to_council failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=3600)
        return existed is None
