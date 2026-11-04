"""
Provider Base Classes

Abstracte basis voor alle providers (email, SMS, payment, etc.)
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class ProviderStatus(str, Enum):
    """Status van een provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ProviderCapability(str, Enum):
    """Capabilities die een provider kan hebben."""

    EMAIL_SEND = "email.send"
    EMAIL_BATCH = "email.batch"
    SMS_SEND = "sms.send"
    WHATSAPP_SEND = "whatsapp.send"
    PUSH_NOTIFICATION = "push.send"
    WEBHOOK_SEND = "webhook.send"
    PAYMENT_PROCESS = "payment.process"
    PAYMENT_REFUND = "payment.refund"


@dataclass
class ProviderResult:
    """
    Resultaat van een provider call.

    Bevat success/failure status, latency, en retry informatie.
    """

    success: bool
    provider_id: str

    # Response data
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None
    error_code: str | None = None

    # Performance metrics
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Retry info
    retry_attempt: int = 0
    max_retries: int = 0

    # Fallback info
    is_fallback: bool = False
    fallback_from: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert naar dictionary."""
        return {
            "success": self.success,
            "provider_id": self.provider_id,
            "data": self.data,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "retry_attempt": self.retry_attempt,
            "is_fallback": self.is_fallback,
        }


@dataclass
class ProviderHealth:
    """Health status van een provider."""

    provider_id: str
    status: ProviderStatus

    # Metrics
    success_rate_5m: float = 1.0
    avg_latency_ms: float = 0.0
    error_count_5m: int = 0

    # Metadata
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_success: datetime | None = None
    last_error: datetime | None = None
    last_error_message: str | None = None

    def is_healthy(self) -> bool:
        """Check of provider healthy is."""
        return self.status == ProviderStatus.HEALTHY

    def can_retry(self) -> bool:
        """Check of retry mogelijk is."""
        return self.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)


class Provider(ABC):
    """
    Abstract base class voor alle providers.

    Providers implementeren concrete communicatie kanalen
    (email, SMS, WhatsApp, payment gateways, etc.)
    """

    def __init__(
        self,
        provider_id: str,
        capabilities: list[ProviderCapability],
        config: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.provider_id = provider_id
        self.capabilities = set(capabilities)
        self.config = config or {}
        self._health = ProviderHealth(provider_id=provider_id, status=ProviderStatus.HEALTHY)
        self._request_count = 0
        self._success_count = 0

    @abstractmethod
    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """
        Execute een capability op deze provider.

        Args:
            capability: Welke capability uit te voeren
            payload: Input data voor de capability
            timeout_ms: Timeout in milliseconden

        Returns:
            ProviderResult met resultaat of error
        """
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """
        Check health van deze provider.

        Returns:
            ProviderHealth met current status
        """
        pass

    def has_capability(self, capability: ProviderCapability) -> bool:
        """Check of deze provider een capability ondersteunt."""
        return capability in self.capabilities

    def get_health(self) -> ProviderHealth:
        """Get current health status."""
        return self._health

    def update_health(self, health: ProviderHealth) -> None:
        """Update health status."""
        self._health = health

    def record_request(self, success: bool, latency_ms: float) -> None:
        """Record een request voor metrics."""
        self._request_count += 1
        if success:
            self._success_count += 1

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self._request_count == 0:
            return 1.0
        return self._success_count / self._request_count

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.provider_id}, caps={self.capabilities})"


# ============================================================================
# Concrete Provider Implementaties (No-Cost voor Demo)
# ============================================================================


class MockEmailProvider(Provider):
    """Mock email provider voor testing/demo."""

    def __init__(self, provider_id: str = "mock_email", failure_rate: float = 0.0) -> None:
        super().__init__(
            provider_id=provider_id,
            capabilities=[
                ProviderCapability.EMAIL_SEND,
                ProviderCapability.EMAIL_BATCH,
            ],
        )
        self.failure_rate = failure_rate

    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """Mock email execution."""
        import random

        start_time = datetime.now(timezone.utc)

        # Simulate failure
        if random.random() < self.failure_rate:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message="Simulated email failure",
                error_code="MOCK_ERROR",
                latency_ms=100.0,
            )

        # Simulate success
        await asyncio.sleep(0.01)  # Simulate latency

        latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        return ProviderResult(
            success=True,
            provider_id=self.provider_id,
            data={
                "message_id": f"msg_{datetime.now(timezone.utc).timestamp()}",
                "to": payload.get("to"),
                "subject": payload.get("subject"),
            },
            latency_ms=latency,
        )

    async def health_check(self) -> ProviderHealth:
        """Mock health check."""
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY if self.failure_rate < 0.5 else ProviderStatus.DEGRADED,
            success_rate_5m=1.0 - self.failure_rate,
        )


class MockSMSProvider(Provider):
    """Mock SMS provider voor testing/demo."""

    def __init__(self, provider_id: str = "mock_sms", failure_rate: float = 0.0) -> None:
        super().__init__(
            provider_id=provider_id,
            capabilities=[ProviderCapability.SMS_SEND],
        )
        self.failure_rate = failure_rate

    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """Mock SMS execution."""
        import random

        if random.random() < self.failure_rate:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message="Simulated SMS failure",
                error_code="MOCK_SMS_ERROR",
            )

        await asyncio.sleep(0.005)

        return ProviderResult(
            success=True,
            provider_id=self.provider_id,
            data={
                "message_id": f"sms_{datetime.now(timezone.utc).timestamp()}",
                "to": payload.get("to"),
                "body": payload.get("body"),
            },
        )

    async def health_check(self) -> ProviderHealth:
        """Mock health check."""
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY,
        )


class MockWhatsAppProvider(Provider):
    """Mock WhatsApp provider voor testing/demo."""

    def __init__(self, provider_id: str = "mock_whatsapp", failure_rate: float = 0.0) -> None:
        super().__init__(
            provider_id=provider_id,
            capabilities=[ProviderCapability.WHATSAPP_SEND],
        )
        self.failure_rate = failure_rate

    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """Mock WhatsApp execution."""
        import random

        if random.random() < self.failure_rate:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message="Simulated WhatsApp failure",
                error_code="MOCK_WA_ERROR",
            )

        await asyncio.sleep(0.008)

        return ProviderResult(
            success=True,
            provider_id=self.provider_id,
            data={
                "message_id": f"wa_{datetime.now(timezone.utc).timestamp()}",
                "to": payload.get("to"),
            },
        )

    async def health_check(self) -> ProviderHealth:
        """Mock health check."""
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY,
        )


class MockWebhookProvider(Provider):
    """Mock webhook provider voor internal notifications."""

    def __init__(self, provider_id: str = "mock_webhook") -> None:
        super().__init__(
            provider_id=provider_id,
            capabilities=[ProviderCapability.WEBHOOK_SEND],
        )

    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """Mock webhook execution."""
        await asyncio.sleep(0.002)

        return ProviderResult(
            success=True,
            provider_id=self.provider_id,
            data={
                "webhook_id": f"wh_{datetime.now(timezone.utc).timestamp()}",
                "endpoint": payload.get("endpoint"),
            },
        )

    async def health_check(self) -> ProviderHealth:
        """Mock health check."""
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY,
        )
