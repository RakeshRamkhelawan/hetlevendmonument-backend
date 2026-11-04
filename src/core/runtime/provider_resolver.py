"""
TKT-F2-01: Provider Resolver + Fallback

Implements provider resolution per tenant policy with primary/fallback.
Integrates with circuit breaker for resilience.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TypeVar, cast
from collections.abc import Callable

from src.core.resilience import CircuitBreaker, CircuitBreakerOpen, get_circuit_breaker

T = TypeVar("T")


class ProviderHealth(Enum):
    """Health status of a provider"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ResolutionOutcome(Enum):
    """Outcome of provider resolution"""

    SUCCESS_PRIMARY = "success_primary"
    SUCCESS_FALLBACK = "success_fallback"
    ALL_PROVIDERS_FAILED = "all_providers_failed"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"


@dataclass
class ProviderDecision:
    """Decision trace for provider selection"""

    decision_id: str
    tenant_id: str
    capability_key: str
    primary_provider: str
    selected_provider: str
    outcome: ResolutionOutcome
    reasoning: str
    latency_ms: float
    fallback_used: bool = False
    circuit_breaker_state: str | None = None
    error_details: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "capability_key": self.capability_key,
            "primary_provider": self.primary_provider,
            "selected_provider": self.selected_provider,
            "outcome": self.outcome.value,
            "reasoning": self.reasoning,
            "latency_ms": self.latency_ms,
            "fallback_used": self.fallback_used,
            "circuit_breaker_state": self.circuit_breaker_state,
            "error_details": self.error_details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Provider:
    """Provider configuration"""

    name: str
    priority: int  # Lower = higher priority (primary = 1)
    capability: str
    handler: Callable[..., Any]  # TODO(TYPE): replace Any with concrete type
    circuit_breaker: CircuitBreaker | None = None
    health: ProviderHealth = ProviderHealth.UNKNOWN

    def __post_init__(self) -> None:
        if self.circuit_breaker is None:
            self.circuit_breaker = get_circuit_breaker(f"provider_{self.name}")


@dataclass
class ProviderChain:
    """Chain of providers for a capability (primary + fallbacks)"""

    capability_key: str
    providers: list[Provider] = field(default_factory=list)

    def add_provider(self, provider: Provider) -> None:
        """Add provider to chain"""
        self.providers.append(provider)
        # Sort by priority
        self.providers.sort(key=lambda p: p.priority)

    def get_primary(self) -> Provider | None:
        """Get primary provider (lowest priority number)"""
        if not self.providers:
            return None
        return self.providers[0]

    def get_fallbacks(self) -> list[Provider]:
        """Get fallback providers (excluding primary)"""
        if len(self.providers) <= 1:
            return []
        return self.providers[1:]


class ProviderResolver:
    """
    Resolves provider calls with fallback support.

    Integrates with circuit breaker for resilience:
    - Tracks provider health
    - Automatically falls back on failure
    - Records decision traces for audit

    Usage:
        resolver = ProviderResolver()
        resolver.register_chain("email.send", primary_provider, fallback_provider)

        decision, result = await resolver.resolve(
            tenant_id="tenant-123",
            capability_key="email.send",
            inputs={"to": "user@test.com"}
        )
    """

    def __init__(self) -> None:
        self._chains: dict[str, ProviderChain] = {}
        self._decisions: list[ProviderDecision] = []
        self._tenant_policies: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def register_chain(self, capability_key: str, *providers: Provider) -> None:
        """
        Register provider chain for a capability.

        Args:
            capability_key: The capability (e.g., "email.send")
            *providers: Providers in priority order (first = primary)
        """
        chain = ProviderChain(capability_key=capability_key)
        for provider in providers:
            chain.add_provider(provider)
        self._chains[capability_key] = chain

    def set_tenant_policy(
        self, tenant_id: str, capability_key: str, allowed_providers: list[str]
    ) -> None:
        """
        Set tenant-specific provider policy.

        Args:
            tenant_id: Tenant identifier
            capability_key: The capability
            allowed_providers: List[Any] of allowed provider names  # TODO(TYPE): replace Any with concrete type
        """
        if tenant_id not in self._tenant_policies:
            self._tenant_policies[tenant_id] = {}
        self._tenant_policies[tenant_id][capability_key] = allowed_providers

    async def resolve(
        self,
        tenant_id: str,
        capability_key: str,
        inputs: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: float = 5000.0,
    ) -> tuple[ProviderDecision, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Resolve capability call with fallback support.

        Args:
            tenant_id: Tenant identifier
            capability_key: The capability to resolve
            inputs: Input parameters
            timeout_ms: Timeout per provider attempt

        Returns: Tuple[Any, ...] of (ProviderDecision, result)  # TODO(TYPE): replace Any with concrete type

        Raises:
            AllProvidersFailedException: If all providers fail
        """
        start_time = time.time()
        decision_id = str(uuid.uuid4())

        # Get provider chain
        chain = self._chains.get(capability_key)
        if not chain or not chain.providers:
            decision = ProviderDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                capability_key=capability_key,
                primary_provider="",
                selected_provider="",
                outcome=ResolutionOutcome.ALL_PROVIDERS_FAILED,
                reasoning="No providers registered for capability",
                latency_ms=(time.time() - start_time) * 1000,
                error_details="No provider chain found",
            )
            self._decisions.append(decision)
            raise NoProviderChainException(f"No providers for {capability_key}")

        primary = chain.get_primary()
        fallbacks = chain.get_fallbacks()

        # Filter by tenant policy
        allowed = self._get_allowed_providers(tenant_id, capability_key)
        all_providers = ([primary] if primary else []) + fallbacks
        candidates = [p for p in all_providers if p.name in allowed or not allowed]

        if not candidates:
            decision = ProviderDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                capability_key=capability_key,
                primary_provider=primary.name if primary else "",
                selected_provider="",
                outcome=ResolutionOutcome.ALL_PROVIDERS_FAILED,
                reasoning="No providers allowed by tenant policy",
                latency_ms=(time.time() - start_time) * 1000,
                error_details="Tenant policy restriction",
            )
            self._decisions.append(decision)
            raise TenantPolicyException(f"No allowed providers for tenant {tenant_id}")

        # Try each provider in order
        last_error = None
        for idx, provider in enumerate(candidates):
            is_fallback = idx > 0

            try:
                # Check circuit breaker
                if provider.circuit_breaker and provider.circuit_breaker.state.value == "open":
                    last_error = f"Circuit open for {provider.name}"
                    continue

                # Attempt call
                provider_start = time.time()

                if provider.circuit_breaker:
                    result = await provider.circuit_breaker.call(provider.handler, inputs)
                else:
                    result = await provider.handler(inputs)

                provider_latency = (time.time() - provider_start) * 1000
                total_latency = (time.time() - start_time) * 1000

                # Success!
                outcome = (
                    ResolutionOutcome.SUCCESS_FALLBACK
                    if is_fallback
                    else ResolutionOutcome.SUCCESS_PRIMARY
                )
                decision = ProviderDecision(
                    decision_id=decision_id,
                    tenant_id=tenant_id,
                    capability_key=capability_key,
                    primary_provider=primary.name if primary else "",
                    selected_provider=provider.name,
                    outcome=outcome,
                    reasoning=f"Successfully called {'fallback ' if is_fallback else ''}provider",
                    latency_ms=total_latency,
                    fallback_used=is_fallback,
                    circuit_breaker_state=(
                        provider.circuit_breaker.state.value if provider.circuit_breaker else None
                    ),
                )
                self._decisions.append(decision)
                return decision, result

            except CircuitBreakerOpen as e:
                last_error = f"Circuit open: {provider.name}"
                continue
            except Exception as e:
                last_error = f"{provider.name}: {str(e)}"
                continue

        # All providers failed
        total_latency = (time.time() - start_time) * 1000
        decision = ProviderDecision(
            decision_id=decision_id,
            tenant_id=tenant_id,
            capability_key=capability_key,
            primary_provider=primary.name if primary else "",
            selected_provider="",
            outcome=ResolutionOutcome.ALL_PROVIDERS_FAILED,
            reasoning="All providers failed",
            latency_ms=total_latency,
            error_details=last_error,
        )
        self._decisions.append(decision)
        raise AllProvidersFailedException(
            f"All providers failed for {capability_key}: {last_error}"
        )

    def _get_allowed_providers(self, tenant_id: str, capability_key: str) -> list[str]:
        """Get allowed providers for tenant"""
        tenant_policy = self._tenant_policies.get(tenant_id, {})
        return cast(list[str], tenant_policy.get(capability_key, []))

    def get_decisions(self, tenant_id: str | None = None) -> list[ProviderDecision]:
        """Get decision history"""
        if tenant_id:
            return [d for d in self._decisions if d.tenant_id == tenant_id]
        return self._decisions.copy()

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get resolver statistics"""
        total = len(self._decisions)
        if total == 0:
            return {"total_decisions": 0}

        primary_success = sum(
            1 for d in self._decisions if d.outcome == ResolutionOutcome.SUCCESS_PRIMARY
        )
        fallback_success = sum(
            1 for d in self._decisions if d.outcome == ResolutionOutcome.SUCCESS_FALLBACK
        )
        failures = sum(
            1 for d in self._decisions if d.outcome == ResolutionOutcome.ALL_PROVIDERS_FAILED
        )

        return {
            "total_decisions": total,
            "primary_success": primary_success,
            "fallback_success": fallback_success,
            "failures": failures,
            "fallback_rate": fallback_success / total * 100 if total > 0 else 0,
            "success_rate": (primary_success + fallback_success) / total * 100 if total > 0 else 0,
        }


class NoProviderChainException(Exception):
    """Raised when no provider chain exists for capability"""

    pass


class TenantPolicyException(Exception):
    """Raised when tenant policy blocks all providers"""

    pass


class AllProvidersFailedException(Exception):
    """Raised when all providers fail"""

    pass
