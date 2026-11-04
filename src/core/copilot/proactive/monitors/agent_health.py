"""AgentHealthMonitor - detects agents with >50% failure rate."""

from __future__ import annotations

import logging
from typing import Any

from src.core.als.health_monitor import ERROR_RATE_CRITICAL, HealthMetrics
from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import (
    HealthMonitorRegistry,
    TenantRepo,
)
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class AgentHealthMonitor(ProactiveMonitor):
    """Detects agents exceeding the critical error-rate threshold."""

    name = "agent_health"
    version = "1.0.0"
    interval_seconds = 300  # 5 min
    default_severity = Severity.MEDIUM

    # Per ADR-027 Officer Timeouts inspiration: dispatch within 30s
    HIGH_FAILURE_COUNT_THRESHOLD = 25

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        health_registry: HealthMonitorRegistry,
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._health_registry = health_registry
        self._tenant_repo = tenant_repo
        self._redis = redis

    async def detect(self, tenant_id: int) -> list[Signal]:
        service = self._health_registry.get_for_tenant(tenant_id)
        if service is None:
            logger.info(
                "agent_health detect: no service for tenant",
                extra={"tenant_id": tenant_id, "monitor": self.name},
            )
            return []

        report: list[HealthMetrics] = service.get_health_report()
        unhealthy = [m for m in report if m.error_rate >= ERROR_RATE_CRITICAL]
        if not unhealthy:
            logger.info(
                "agent_health detect: all healthy",
                extra={"tenant_id": tenant_id, "monitor": self.name, "signal_count": 0},
            )
            return []

        admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
        signals: list[Signal] = []
        for metrics in unhealthy:
            if await self._is_duplicate(tenant_id, metrics.agent_id):
                continue
            severity = (
                Severity.HIGH
                if metrics.error_count >= self.HIGH_FAILURE_COUNT_THRESHOLD
                else Severity.MEDIUM
            )
            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"Agent {metrics.agent_id} faalt {metrics.error_count}x",
                    # Als aantallen, niet als percentage (OP-171, 2026-08-27): de
                    # fabricated-stat-regex in HallucinationGuard matcht sinds die fix ook
                    # losse percentages (`\d{2,3}%`), en deze tekst gaat ongewijzigd door
                    # naar de SanityOfficer via Proposal.reasoning/message. Een systeem-
                    # berekend percentage is geen hallucinatie, maar de regex kan dat
                    # onderscheid niet maken -- de fix hoort hier, niet in de guard.
                    body=(
                        f"Agent '{metrics.agent_id}' faalde {metrics.error_count} van de "
                        f"{metrics.total_tasks} aanroepen."
                    ),
                    severity=severity,
                    data_classification=DataClassification.INTERNAL,
                    suggested_actions=[
                        {
                            "label": "Bekijk agent details",
                            "action": "navigate_to",
                            "params": {"route": f"/agents/{metrics.agent_id}"},
                        },
                        {
                            "label": "Restart agent",
                            "action": "restart_agent",
                            "params": {"agent_id": metrics.agent_id},
                        },
                    ],
                    detection_reasoning=(
                        f"Agent failure rate ({metrics.error_count}/{metrics.total_tasks}) "
                        f"overschrijdt de kritieke drempel"
                    ),
                    confidence=0.95,
                    context={
                        "agent_id": metrics.agent_id,
                        "failure_count": metrics.error_count,
                        "total_tasks": metrics.total_tasks,
                    },
                )
            )

        logger.info(
            "agent_health detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
                "threshold": ERROR_RATE_CRITICAL,
            },
        )

        # Emit metrics via best_effort so a metrics failure does not block detection
        async with best_effort("agent_health metrics"):
            pass  # placeholder for Prometheus counter increment if needed

        return signals

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
