"""SensitiveWorkflowMonitor -- daily scan for active workflows containing PII fields."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import (
    DPIARepo,
    TenantRepo,
    WorkflowPIIScanner,
    WorkflowRepo,
)
from src.core.copilot.proactive.types import Signal

logger = logging.getLogger(__name__)


class SensitiveWorkflowMonitor(ProactiveMonitor):
    """Scheduled daily scan: detects active workflows with PII fields and no DPIA.

    PolicyChangeMonitor (event-driven) catches config changes in real time.
    This monitor provides catch-all coverage for workflows that were configured
    before PolicyChangeMonitor was active, or whose PII status was introduced
    outside a workflow.config_updated event.
    """

    name = "sensitive_workflow"
    version = "1.0.0"
    interval_seconds = 86_400  # 1x per day
    default_severity = Severity.MEDIUM

    DEDUP_TTL_SECONDS = 86_400  # 24h -- re-alert at most once per day per workflow

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
        workflow_repo: WorkflowRepo,
        pii_scanner: WorkflowPIIScanner,
        dpia_repo: DPIARepo,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_repo = tenant_repo
        self._redis = redis
        self._workflow_repo = workflow_repo
        self._pii_scanner = pii_scanner
        self._dpia_repo = dpia_repo

    async def detect(self, tenant_id: int) -> list[Signal]:
        try:
            workflows = await self._workflow_repo.list_active(tenant_id=tenant_id)
        except Exception as exc:
            logger.error(
                "sensitive_workflow: failed to list active workflows: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return []

        try:
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        except Exception as exc:
            logger.error(
                "sensitive_workflow: failed to get admin user id: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return []

        signals: list[Signal] = []
        for wf in workflows:
            wf_id = wf.id if hasattr(wf, "id") else wf.get("id")
            wf_name = wf.name if hasattr(wf, "name") else wf.get("name", str(wf_id))
            config = wf.config if hasattr(wf, "config") else wf.get("config", {})

            if not wf_id:
                logger.warning(
                    "sensitive_workflow: skipping workflow with missing id",
                    extra={"tenant_id": tenant_id, "monitor": self.name},
                )
                continue

            pii_fields = self._pii_scanner.scan(config)
            if not pii_fields:
                continue

            try:
                if await self._dpia_repo.exists_for_workflow(tenant_id, wf_id):
                    continue
            except Exception as exc:
                logger.error(
                    "sensitive_workflow: dpia_repo check failed for %s: %s: %s",
                    wf_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={"tenant_id": tenant_id, "monitor": self.name},
                )
                # Fail-open: if DPIA check fails, still emit signal to avoid
                # silently missing a workflow that needs review.

            if await self._is_duplicate(tenant_id, str(wf_id)):
                continue

            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"Workflow '{wf_name}' verwerkt persoonsgegevens zonder DPIA",
                    body=(
                        f"Workflow '{wf_name}' (id={wf_id}) bevat PII-velden "
                        f"({', '.join(pii_fields)}) en heeft nog geen DPIA. "
                        f"GDPR/AI Act vereisen vastlegging voordat verwerking plaatsvindt."
                    ),
                    severity=Severity.MEDIUM,
                    data_classification=DataClassification.CONFIDENTIAL,
                    suggested_actions=[
                        {
                            "label": "Start DPIA template",
                            "action": "navigate_to",
                            "params": {"route": f"/compliance/dpia/new?workflow_id={wf_id}"},
                        },
                        {
                            "label": "Bekijk workflow",
                            "action": "navigate_to",
                            "params": {"route": f"/workflows/{wf_id}"},
                        },
                        {
                            "label": "Markeer als niet-PII",
                            "action": "mark_workflow_non_pii",
                            "params": {"workflow_id": wf_id},
                        },
                    ],
                    detection_reasoning=(
                        f"Workflow config references PII fields {pii_fields} "
                        f"and no DPIA exists for workflow_id={wf_id}"
                    ),
                    confidence=0.95,
                    context={
                        "workflow_id": wf_id,
                        "workflow_name": wf_name,
                        "pii_fields": pii_fields,
                    },
                )
            )

        logger.info(
            "sensitive_workflow detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
                "workflows_scanned": len(workflows),
            },
        )
        return signals

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.DEDUP_TTL_SECONDS)
        return existed is None
