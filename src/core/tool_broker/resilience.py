"""
Re-export shim voor backwards compatibiliteit -- SP-DSM-015 dag 1.

Canonical locatie: src/core/resilience/tool_broker_resilience.py (infra-laag).
Verwijder deze shim pas als alle directe callers bijgewerkt zijn (SP-DSM-016 cleanup).
"""

import random  # noqa: F401
from typing import Any, TypeVar  # noqa: F401

from src.core.shared.tool_broker_resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    ResilienceException,
    ResilienceMetrics,
    RetryConfig,
    RetryExhaustedException,
    RetryMetrics,
    async_retry,
    get_circuit_breaker_registry,
    get_resilience_metrics,
    retry_decorator,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenException",
    "CircuitBreakerRegistry",
    "CircuitBreakerState",
    "ResilienceException",
    "ResilienceMetrics",
    "RetryConfig",
    "RetryExhaustedException",
    "RetryMetrics",
    "async_retry",
    "get_circuit_breaker_registry",
    "get_resilience_metrics",
    "retry_decorator",
]
