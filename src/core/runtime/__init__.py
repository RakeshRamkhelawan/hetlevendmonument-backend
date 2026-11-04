"""
Fase 2 Connector Runtime & Notifications

Provides:
- Provider Resolver with fallback (TKT-F2-01)
- Notification Abstraction Layer (TKT-F2-02)
- Builder Preflight Validation (TKT-F2-03)
"""

from typing import Any

from .notification_layer import (
    DeliveryStatus,
    InMemoryChannelHandler,
    NotificationChannel,
    NotificationResult,
    NotificationService,
)
from .preflight_validator import (
    PreflightResult,
    PreflightValidator,
    ValidationCheck,
    ValidationSeverity,
)
from .provider_resolver import (
    AllProvidersFailedException,
    Provider,
    ProviderChain,
    ProviderDecision,
    ProviderHealth,
    ProviderResolver,
    ResolutionOutcome,
)

__all__ = [
    # Provider Resolver
    "Provider",
    "ProviderResolver",
    "ProviderChain",
    "ProviderDecision",
    "ProviderHealth",
    "ResolutionOutcome",
    "AllProvidersFailedException",
    # Notification Layer
    "NotificationService",
    "NotificationChannel",
    "DeliveryStatus",
    "NotificationResult",
    "InMemoryChannelHandler",
    # Preflight Validator
    "PreflightValidator",
    "ValidationCheck",
    "PreflightResult",
    "ValidationSeverity",
]
