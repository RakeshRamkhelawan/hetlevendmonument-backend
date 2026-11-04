"""
Connector Runtime - Fase 2

Provider binding, fallback strategieen, en multi-channel orchestration.
"""

from typing import Any

from src.core.connectors.brevo import BrevoClient, BrevoEmailError, BrevoEmailProvider
from src.core.connectors.circuit_breaker import CircuitBreaker, CircuitState
from src.core.connectors.notification import (
    NotificationChannel,
    NotificationResult,
    NotificationService,
)
from src.core.connectors.provider import (
    Provider,
    ProviderCapability,
    ProviderResult,
    ProviderStatus,
)
from src.core.connectors.resolver import ProviderPriority, ProviderResolver, ResolutionResult

__all__ = [
    # Provider
    "Provider",
    "ProviderResult",
    "ProviderStatus",
    "ProviderCapability",
    # Brevo
    "BrevoClient",
    "BrevoEmailProvider",
    "BrevoEmailError",
    # Resolver
    "ProviderResolver",
    "ProviderPriority",
    "ResolutionResult",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    # Notification
    "NotificationChannel",
    "NotificationService",
    "NotificationResult",
]
