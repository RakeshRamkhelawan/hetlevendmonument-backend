"""TokenSpikeMonitor - detects token usage >2x daily average."""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import PrometheusClient, TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class TokenSpikeMonitor(ProactiveMonitor):
    """Detects daily token usage exceeding a multiple of the baseline average."""

    name = "token_spike"
    version = "1.0.0"
    interval_seconds = 3600  # 1h
    default_severity = Severity.HIGH

    SPIKE_MULTIPLIER = 2.0
    MIN_TOKENS_FOR_SIGNAL = 100_000  # anti-noise for new tenants

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
        tokens_today = await self._prom.get_counter_sum(
            metric_name="llm_tokens_total",
            labels={"tenant_id": str(tenant_id)},
            since="1d",
        )
        if tokens_today < self.MIN_TOKENS_FOR_SIGNAL:
            logger.info(
                "token_spike detect: below min tokens",
                extra={
                    "tenant_id": tenant_id,
                    "monitor": self.name,
                    "tokens_today": tokens_today,
                    "min_threshold": self.MIN_TOKENS_FOR_SIGNAL,
                },
            )
            return []  # anti-noise
        baseline_avg = await self._prom.get_counter_average(
            metric_name="llm_tokens_total",
            labels={"tenant_id": str(tenant_id)},
            window="7d",
            bucket="1d",
        )
        if baseline_avg <= 0 or tokens_today < baseline_avg * self.SPIKE_MULTIPLIER:
            return []
        if await self._is_duplicate(tenant_id, "daily"):
            return []

        ratio = tokens_today / baseline_avg
        admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)

        logger.info(
            "token_spike detect: signal emitted",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": 1,
                "tokens_today": tokens_today,
                "baseline_avg": baseline_avg,
                "ratio": ratio,
            },
        )

        async with best_effort("token_spike metrics"):
            pass

        return [
            Signal(
                tenant_id=tenant_id,
                affected_user_id=admin_user_id,
                monitor_name=self.name,
                title=f"Token-gebruik is {ratio:.1f}x hoger dan normaal",
                body=(
                    f"Vandaag {tokens_today:,.0f} tokens verbruikt "
                    f"(gemiddeld {baseline_avg:,.0f}). Review aanbevolen."
                ),
                severity=Severity.HIGH,
                data_classification=DataClassification.INTERNAL,
                suggested_actions=[
                    {
                        "label": "Bekijk token-gebruik",
                        "action": "navigate_to",
                        "params": {"route": "/admin/billing/tokens"},
                    },
                    {
                        "label": "Stel limiet in",
                        "action": "set_token_cap",
                        "params": {"tenant_id": tenant_id},
                    },
                ],
                detection_reasoning=(
                    f"Token usage {tokens_today:,.0f} is {ratio:.2f}x baseline "
                    f"{baseline_avg:,.0f} (drempel {self.SPIKE_MULTIPLIER}x)"
                ),
                confidence=0.85,
                context={
                    "tokens_today": tokens_today,
                    "baseline_avg": baseline_avg,
                    "ratio": ratio,
                },
            )
        ]

    async def _is_duplicate(self, tenant_id: int, entity_id: str) -> bool:
        key = f"monitor_dedup:{self.name}:{tenant_id}:{entity_id}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
