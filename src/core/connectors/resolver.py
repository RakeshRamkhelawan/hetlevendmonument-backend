"""
Provider Resolver + Fallback Strategie

Kiest de beste provider op basis van:
- Tenant policy priority
- Provider health status
- Circuit breaker state
- Latency metrics
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from collections.abc import Callable

from src.core.connectors.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from src.core.connectors.provider import (
    Provider,
    ProviderCapability,
    ProviderResult,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderPriority:
    """Priority configuratie voor een provider."""

    provider_id: str
    priority: int  # 1 = highest, hoger = lager
    weight: int = 100  # Voor weighted load balancing
    enabled: bool = True


@dataclass
class ResolutionResult:
    """
    Resultaat van provider resolution.

    Bevat gekozen provider of fallback chain.
    """

    success: bool
    capability: ProviderCapability

    # Primary result
    provider_id: str | None = None
    result: ProviderResult | None = None

    # Fallback chain
    attempts: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    fallback_used: bool = False
    fallback_from: str | None = None

    # Metadata
    resolution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert naar dictionary."""
        return {
            "success": self.success,
            "capability": self.capability.value,
            "provider_id": self.provider_id,
            "fallback_used": self.fallback_used,
            "attempts": len(self.attempts),
            "resolution_time_ms": self.resolution_time_ms,
        }


class ProviderResolver:
    """
    Resolver voor provider selectie met fallback.

    Features:
    - Priority-based selection
    - Health-aware routing
    - Circuit breaker integration
    - Automatic failover
    - Latency-based routing
    """

    def __init__(
        self,
        tenant_id: str,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._providers: dict[str, Provider] = {}
        self._priorities: dict[ProviderCapability, list[ProviderPriority]] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._cb_config = circuit_breaker_config or CircuitBreakerConfig()

        # Metrics
        self._resolution_count = 0
        self._fallback_count = 0

    def register_provider(
        self,
        provider: Provider,
        priority: int = 10,
        capabilities: list[ProviderCapability] | None = None,
    ) -> None:
        """
        Registreer een provider.

        Args:
            provider: Provider instance
            priority: Priority (1 = highest)
            capabilities: Welke capabilities te registreren (default: alle)
        """
        self._providers[provider.provider_id] = provider

        # Create circuit breaker
        self._circuit_breakers[provider.provider_id] = CircuitBreaker(
            name=f"{self.tenant_id}_{provider.provider_id}",
            config=self._cb_config,
        )

        # Register capabilities
        caps = capabilities or list(provider.capabilities)
        for cap in caps:
            if cap not in self._priorities:
                self._priorities[cap] = []

            # Add or update priority
            existing = next(
                (p for p in self._priorities[cap] if p.provider_id == provider.provider_id), None
            )
            if existing:
                existing.priority = priority
            else:
                self._priorities[cap].append(
                    ProviderPriority(
                        provider_id=provider.provider_id,
                        priority=priority,
                    )
                )

            # Sort by priority
            self._priorities[cap].sort(key=lambda p: p.priority)

        logger.info(f"Registered provider {provider.provider_id} with priority {priority}")

    def set_provider_priority(
        self,
        capability: ProviderCapability,
        provider_priorities: list[ProviderPriority],
    ) -> None:
        """
        Set provider priority lijst voor een capability.

        Args:
            capability: Welke capability
            provider_priorities: Lijst van ProviderPriority
        """
        # Validate all providers exist
        for pp in provider_priorities:
            if pp.provider_id not in self._providers:
                raise ValueError(f"Unknown provider: {pp.provider_id}")

        self._priorities[capability] = sorted(provider_priorities, key=lambda p: p.priority)

    async def resolve_and_execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
        max_attempts: int = 3,
    ) -> ResolutionResult:
        """
        Resolve beste provider en execute.

        Args:
            capability: Welke capability uit te voeren
            payload: Input data
            timeout_ms: Timeout per attempt
            max_attempts: Max aantal providers om te proberen

        Returns:
            ResolutionResult met resultaat of failure
        """
        start_time = datetime.now(timezone.utc)
        self._resolution_count += 1

        result = ResolutionResult(
            success=False,
            capability=capability,
            attempts=[],
        )

        # Get prioritized providers
        providers = self._get_providers_for_capability(capability)

        if not providers:
            result.attempts.append(
                {
                    "error": f"No providers available for capability {capability.value}",
                }
            )
            result.resolution_time_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return result

        # Try providers in order
        last_error = None
        for i, (provider, priority) in enumerate(providers[:max_attempts]):
            provider_id = provider.provider_id
            circuit_breaker = self._circuit_breakers.get(provider_id)

            # Check circuit breaker
            if circuit_breaker and not circuit_breaker.can_execute():
                result.attempts.append(
                    {
                        "provider_id": provider_id,
                        "skipped": True,
                        "reason": "circuit_open",
                    }
                )
                continue

            # Check health
            health = provider.get_health()
            if health.status == ProviderStatus.DISABLED:
                result.attempts.append(
                    {
                        "provider_id": provider_id,
                        "skipped": True,
                        "reason": "disabled",
                    }
                )
                continue

            # Try execution
            try:
                provider_result = await provider.execute(
                    capability=capability,
                    payload=payload,
                    timeout_ms=timeout_ms,
                )

                # Record result
                if provider_result.success:
                    # Success!
                    if circuit_breaker:
                        circuit_breaker.record_success()

                    result.success = True
                    result.provider_id = provider_id
                    result.result = provider_result

                    # Track fallback
                    if i > 0:
                        result.fallback_used = True
                        result.fallback_from = providers[0][0].provider_id
                        self._fallback_count += 1

                    break
                else:
                    # Provider returned failure
                    if circuit_breaker:
                        circuit_breaker.record_failure(provider_result.error_message)

                    result.attempts.append(
                        {
                            "provider_id": provider_id,
                            "success": False,
                            "error": provider_result.error_message,
                            "error_code": provider_result.error_code,
                        }
                    )
                    last_error = provider_result.error_message

            except Exception as e:
                # Exception during execution
                error_msg = str(e)
                if circuit_breaker:
                    circuit_breaker.record_failure(error_msg)

                result.attempts.append(
                    {
                        "provider_id": provider_id,
                        "success": False,
                        "error": error_msg,
                        "exception": True,
                    }
                )
                last_error = error_msg
                logger.exception(f"Error executing {capability.value} on {provider_id}")

        # Calculate resolution time
        result.resolution_time_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        if not result.success:
            logger.warning(
                f"All providers failed for {capability.value} "
                f"(attempts: {len(result.attempts)})"
            )

        return result

    def _get_providers_for_capability(
        self,
        capability: ProviderCapability,
    ) -> list[tuple[Any, ...]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get providers voor een capability, gesorteerd op priority.

        Returns:
            Lijst van (provider, priority) tuples
        """
        if capability not in self._priorities:
            return []

        result: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pp in self._priorities[capability]:
            if not pp.enabled:
                continue

            provider = self._providers.get(pp.provider_id)
            if provider and provider.has_capability(capability):
                result.append((provider, pp.priority))

        return result

    def get_circuit_breaker(self, provider_id: str) -> CircuitBreaker | None:
        """Get circuit breaker voor een provider."""
        return self._circuit_breakers.get(provider_id)

    def get_all_circuit_breaker_stats(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get stats van alle circuit breakers."""
        return {name: cb.get_stats() for name, cb in self._circuit_breakers.items()}

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get resolver metrics."""
        return {
            "tenant_id": self.tenant_id,
            "resolution_count": self._resolution_count,
            "fallback_count": self._fallback_count,
            "fallback_rate": (
                self._fallback_count / self._resolution_count if self._resolution_count > 0 else 0.0
            ),
            "provider_count": len(self._providers),
            "circuit_breaker_stats": self.get_all_circuit_breaker_stats(),
        }
