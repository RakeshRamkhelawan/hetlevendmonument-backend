"""CircuitBreakerMonitor - detects OPEN state on FailoverLLMProvider chain."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.monitors.protocols import TenantRepo
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class FailoverProvider(Protocol):
    """Minimal protocol for FailoverLLMProvider circuit-state inspection."""

    async def get_circuit_states(self) -> dict[str, str]:
        """Return current circuit breaker states per provider key."""
        ...


class CircuitBreakerMonitor(ProactiveMonitor):
    """Detects OPEN circuit breakers in the LLM failover chain."""

    name = "circuit_breaker"
    version = "1.0.0"
    interval_seconds = 60  # 1 min - fast reaction to provider-down
    default_severity = Severity.HIGH

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        failover_provider: FailoverProvider,
        tenant_repo: TenantRepo,
        redis: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._failover = failover_provider
        self._tenant_repo = tenant_repo
        self._redis = redis

    async def detect(self, tenant_id: int) -> list[Signal]:
        # Prevent N-tenants-N-signals: only the platform-admin tenant
        # receives circuit breaker signals (state is process-global).
        platform_tenant = await self._tenant_repo.get_platform_admin_tenant_id()
        if tenant_id != platform_tenant:
            return []

        states = await self._failover.get_circuit_states()
        # states: dict[str, str] - e.g. {"DeepSeekProvider#0": "open",
        #                                 "AnthropicProvider#1": "closed"}
        signals: list[Signal] = []
        for breaker_key, state in states.items():
            if state.lower() != "open":
                continue
            # Global dedup-key (no tenant_id in key) so one OPEN
            # breaker produces exactly 1 signal per 2 min total.
            if await self._is_duplicate_global(breaker_key):
                continue
            # Provider name without index (DeepSeekProvider#0 -> DeepSeekProvider)
            provider_name = breaker_key.split("#")[0]
            is_primary = breaker_key.endswith("#0")
            severity = Severity.HIGH if is_primary else Severity.MEDIUM
            admin_user_id = await self._tenant_repo.get_primary_admin_user_id(tenant_id)
            signals.append(
                Signal(
                    tenant_id=tenant_id,
                    affected_user_id=admin_user_id,
                    monitor_name=self.name,
                    title=f"LLM provider {provider_name} is onbereikbaar",
                    body=(
                        f"Circuit breaker voor {breaker_key} staat OPEN. "
                        f"{'Primaire' if is_primary else 'Backup'}-provider is "
                        f"gemarkeerd als down -- failover chain is actief naar de "
                        f"volgende provider. Kosten kunnen anders zijn."
                    ),
                    severity=severity,
                    data_classification=DataClassification.INTERNAL,
                    suggested_actions=[
                        {
                            "label": "Bekijk circuit states",
                            "action": "navigate_to",
                            "params": {"route": "/admin/llm/providers"},
                        },
                        {
                            "label": "Forceer recovery",
                            "action": "reset_circuit",
                            "params": {"breaker_key": breaker_key},
                        },
                    ],
                    detection_reasoning=(
                        f"CircuitBreaker '{breaker_key}' state is OPEN; "
                        f"FailoverLLMProvider gebruikt nu de volgende provider "
                        f"in de chain."
                    ),
                    confidence=1.0,
                    context={
                        "breaker_key": breaker_key,
                        "state": state,
                        "is_primary": is_primary,
                    },
                )
            )

        logger.info(
            "circuit_breaker detect complete",
            extra={
                "tenant_id": tenant_id,
                "monitor": self.name,
                "signal_count": len(signals),
            },
        )

        async with best_effort("circuit_breaker metrics"):
            pass

        return signals

    async def _is_duplicate_global(self, breaker_key: str) -> bool:
        """Process-global dedup: 1 signal per OPEN breaker per 2 min."""
        key = f"monitor_dedup:{self.name}:GLOBAL:{breaker_key}"
        existed = await self._redis.set(key, "1", nx=True, ex=self.interval_seconds * 2)
        return existed is None
