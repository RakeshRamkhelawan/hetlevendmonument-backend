"""QueueDepthMonitor - detects Dramatiq queue depth >1000 messages."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class QueueDepthMonitor(ProactiveMonitor):
    """Detects Dramatiq queues exceeding depth thresholds."""

    name = "queue_depth"
    version = "1.0.0"
    interval_seconds = 300  # 5 min
    default_severity = Severity.MEDIUM

    DEPTH_MEDIUM = 1000
    DEPTH_HIGH = 5000
    DEPTH_CRITICAL = 10000

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
        queue_names: list[str],
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_repo = tenant_repo
        self._redis = redis
        self._queue_names = queue_names  # explicit config, no wildcards

    async def detect(self, tenant_id: int) -> list[Signal]:
        signals: list[Signal] = []
        for queue_name in self._queue_names:
            depth = await self._redis.llen(f"dramatiq:{queue_name}")
            if depth < self.DEPTH_MEDIUM:
                continue
            if await self._is_duplicate(tenant_id, queue_name):
                continue
            severity = self._depth_to_severity(depth)
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"Queue {queue_name} heeft {depth} berichten",
                    body=(
                        f"Dramatiq queue '{queue_name}' bevat {depth} berichten "
                        f"(drempel {self.DEPTH_MEDIUM}). Workers mogelijk overbelast."
                    ),
                    severity=severity,
                    data_classification=DataClassification.INTERNAL,
                    suggested_actions=[
                        {
                            "label": "Bekijk worker metrics",
                            "action": "navigate_to",
                            "params": {"route": "/admin/workers"},
                        },
                        {
                            "label": "Schaal workers op",
                            "action": "scale_workers",
                            "params": {"queue": queue_name, "delta": 1},
                        },
                    ],
                    detection_reasoning=(
                        f"Queue depth {depth} overschrijdt drempel "
                        f"{self.DEPTH_MEDIUM} (severity {severity.value})"
                    ),
                    confidence=1.0,
                    context={"queue": queue_name, "depth": depth},
                )
            )

        logger.info(
            "queue_depth detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
                "threshold": self.DEPTH_MEDIUM,
            },
        )

        async with best_effort("queue_depth metrics"):
            pass

        return signals

    def _depth_to_severity(self, depth: int) -> Severity:
        if depth >= self.DEPTH_CRITICAL:
            return Severity.CRITICAL
        if depth >= self.DEPTH_HIGH:
            return Severity.HIGH
        return Severity.MEDIUM

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
