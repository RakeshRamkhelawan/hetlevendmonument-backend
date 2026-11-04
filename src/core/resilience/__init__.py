"""
Resilience Module - Circuit Breaker, Retry Policy, and Fault Tolerance

Provides:
- Circuit breaker pattern for failing services
- Configurable retry policies
- Bulkhead isolation (future)
- Rate limiting integration
"""

from dataclasses import dataclass
from typing import Any, cast

from .circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .retry_policy import RetryPolicy, RetryStrategy

# Backward compatibility alias (some tests use CircuitBreakerOpen)
CircuitBreakerOpen = CircuitOpenError


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Backward-compatible config container for circuit breaker settings."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0


_breaker_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


def get_circuit_breaker(
    provider: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Backward-compatible helper returning a cached circuit breaker per provider."""
    if provider not in _breaker_cache:
        _breaker_cache[provider] = CircuitBreaker(
            provider=provider,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return cast(CircuitBreaker, _breaker_cache[provider])


__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "CircuitBreakerOpen",  # Backward compatibility
    "CircuitBreakerConfig",
    "get_circuit_breaker",
    "RetryPolicy",
    "RetryStrategy",
]
