"""WorkflowLatencyMonitor - detects P95 latency >3x baseline."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import PrometheusClient, TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class WorkflowLatencyMonitor(ProactiveMonitor):
    """Detects workflows whose P95 latency exceeds a multiple of baseline."""

    name = "workflow_latency"
    version = "1.0.0"
    interval_seconds = 600  # 10 min
    default_severity = Severity.MEDIUM

    P95_MULTIPLIER_THRESHOLD = 3.0
    P95_MULTIPLIER_HIGH = 5.0
    MIN_EXECUTIONS_FOR_SIGNAL = 10

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        prom_client: PrometheusClient,
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._prom = prom_client
        self._tenant_repo = tenant_repo
        self._redis = redis

    async def detect(self, tenant_id: int) -> list[Signal]:
        workflows = await self._prom.list_workflows(tenant_id=tenant_id)
        signals: list[Signal] = []
        for wf in workflows:
            wf_id = str(getattr(wf, "id", wf))
            wf_name = str(getattr(wf, "name", wf_id))
            execs_today = await self._prom.execution_count(
                workflow_id=wf_id, tenant_id=tenant_id, since="1d"
            )
            if execs_today < self.MIN_EXECUTIONS_FOR_SIGNAL:
                continue  # anti-noise for rare workflows
            p95_today = await self._prom.get_histogram_p95(
                metric_name="workflow_execution_duration_seconds",
                labels={"tenant_id": str(tenant_id), "workflow_id": wf_id},
                since="1d",
            )
            baseline = await self._prom.get_histogram_p95(
                metric_name="workflow_execution_duration_seconds",
                labels={"tenant_id": str(tenant_id), "workflow_id": wf_id},
                since="7d",
            )
            if baseline <= 0 or p95_today < baseline * self.P95_MULTIPLIER_THRESHOLD:
                continue
            if await self._is_duplicate(tenant_id, wf_id):
                continue
            ratio = p95_today / baseline
            severity = Severity.HIGH if ratio >= self.P95_MULTIPLIER_HIGH else Severity.MEDIUM
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"Workflow {wf_name} is {ratio:.1f}x trager dan normaal",
                    body=(
                        f"P95 vandaag is {p95_today:.2f}s, baseline (7d) is "
                        f"{baseline:.2f}s. {execs_today} executions vandaag."
                    ),
                    severity=severity,
                    data_classification=DataClassification.INTERNAL,
                    suggested_actions=[
                        {
                            "label": "Bekijk workflow runs",
                            "action": "navigate_to",
                            "params": {"route": f"/workflows/{wf_id}/runs"},
                        },
                        {
                            "label": "Snooze 1u",
                            "action": "snooze_signal",
                            "params": {"duration_seconds": 3600},
                        },
                    ],
                    detection_reasoning=(
                        f"P95 ratio {ratio:.2f}x overschrijdt threshold "
                        f"{self.P95_MULTIPLIER_THRESHOLD}x bij {execs_today} executions"
                    ),
                    confidence=0.90,
                    context={
                        "workflow_id": wf_id,
                        "p95_today": p95_today,
                        "baseline": baseline,
                        "ratio": ratio,
                    },
                )
            )

        logger.info(
            "workflow_latency detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
                "threshold": self.P95_MULTIPLIER_THRESHOLD,
            },
        )

        async with best_effort("workflow_latency metrics"):
            pass

        return signals

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
