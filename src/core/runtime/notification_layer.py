"""
TKT-F2-02: Notification Abstraction Layer

Implements uniform notify contract for email/whatsapp/internal.
Provides delivery statuses and idempotency keys.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from collections.abc import Callable


class NotificationChannel(Enum):
    """Supported notification channels"""

    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    INTERNAL = "internal"
    WEBHOOK = "webhook"


class DeliveryStatus(Enum):
    """Delivery status for notifications"""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_PERMANENT = "failed_permanent"
    RETRYING = "retrying"
    ESCALATED = "escalated"


@dataclass
class NotificationResult:
    """Result of notification attempt"""

    notification_id: str
    idempotency_key: str
    channel: NotificationChannel
    status: DeliveryStatus
    recipient: str
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def is_success(self) -> bool:
        """Check if notification was successful"""
        return self.status in [DeliveryStatus.SENT, DeliveryStatus.DELIVERED, DeliveryStatus.READ]

    def is_failed(self) -> bool:
        """Check if notification failed permanently"""
        return self.status == DeliveryStatus.FAILED_PERMANENT

    def can_retry(self) -> bool:
        """Check if notification can be retried"""
        return (
            self.status == DeliveryStatus.FAILED_TRANSIENT and self.retry_count < self.max_retries
        )

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "notification_id": self.notification_id,
            "idempotency_key": self.idempotency_key,
            "channel": self.channel.value,
            "status": self.status.value,
            "recipient": self.recipient,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }


class ChannelHandler(Protocol):
    """Protocol for channel handlers"""

    async def send(
        self, recipient: str, content: str, metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> NotificationResult:
        """Send notification via this channel"""
        ...


@dataclass
class ChannelConfig:
    """Configuration for a notification channel"""

    channel: NotificationChannel
    handler: ChannelHandler
    enabled: bool = True
    max_retries: int = 3
    retry_delays: list[float] = field(default_factory=lambda: [1.0, 5.0, 15.0])  # seconds
    timeout_ms: float = 5000.0


class InMemoryChannelHandler:
    """In-memory handler for testing/demo purposes"""

    def __init__(self, channel: NotificationChannel, simulate_failure: bool = False) -> None:
        self.channel = channel
        self.simulate_failure = simulate_failure
        self.sent_notifications: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    async def send(
        self, recipient: str, content: str, metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> NotificationResult:
        """Simulate sending notification"""
        notification_id = str(uuid.uuid4())
        idempotency_key = metadata.get(
            "idempotency_key", self._generate_idempotency_key(recipient, content)
        )

        # Check for duplicate (idempotency)
        existing = self._find_by_idempotency(idempotency_key)
        if existing:
            return existing

        # Simulate failure if configured
        if self.simulate_failure:
            result = NotificationResult(
                notification_id=notification_id,
                idempotency_key=idempotency_key,
                channel=self.channel,
                status=DeliveryStatus.FAILED_TRANSIENT,
                recipient=recipient,
                error_message="Simulated transient failure",
                metadata=metadata,
            )
        else:
            result = NotificationResult(
                notification_id=notification_id,
                idempotency_key=idempotency_key,
                channel=self.channel,
                status=DeliveryStatus.SENT,
                recipient=recipient,
                sent_at=datetime.now(timezone.utc),
                metadata=metadata,
            )

        self.sent_notifications.append(result.to_dict())
        return result

    def _generate_idempotency_key(self, recipient: str, content: str) -> str:
        """Generate idempotency key from content"""
        key_data = f"{recipient}:{content}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _find_by_idempotency(self, key: str) -> NotificationResult | None:
        """Find existing notification by idempotency key"""
        for notif in self.sent_notifications:
            if notif.get("idempotency_key") == key:
                # Reconstruct result
                return NotificationResult(
                    notification_id=notif["notification_id"],
                    idempotency_key=notif["idempotency_key"],
                    channel=NotificationChannel(notif["channel"]),
                    status=DeliveryStatus(notif["status"]),
                    recipient=notif["recipient"],
                    sent_at=(
                        datetime.fromisoformat(notif["sent_at"]) if notif.get("sent_at") else None
                    ),
                    metadata=notif.get("metadata", {}),
                )
        return None


class NotificationService:
    """
    Unified notification service supporting multiple channels.

    Features:
    - Idempotency keys for duplicate prevention
    - Automatic retry with exponential backoff
    - Escalation on permanent failure
    - Audit trail for all attempts

    Usage:
        service = NotificationService()
        service.register_channel(NotificationChannel.EMAIL, email_handler)

        result = await service.notify(
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            content="Hello!",
            idempotency_key="unique-key-123"
        )
    """

    def __init__(self) -> None:
        self._channels: dict[NotificationChannel, ChannelConfig] = {}
        self._results: list[NotificationResult] = []
        self._escalation_handlers: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

    def register_channel(
        self, channel: NotificationChannel, handler: ChannelHandler, max_retries: int = 3
    ) -> None:
        """
        Register a channel handler.

        Args:
            channel: The notification channel
            handler: Handler implementation
            max_retries: Maximum retry attempts
        """
        self._channels[channel] = ChannelConfig(
            channel=channel,
            handler=handler,
            max_retries=max_retries,
        )

    def register_escalation_handler(self, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register handler for escalated notifications"""
        self._escalation_handlers.append(handler)

    async def notify(
        self,
        channel: NotificationChannel,
        recipient: str,
        content: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> NotificationResult:
        """
        Send notification with retry and escalation.

        Args:
            channel: Channel to use
            recipient: Recipient address/number
            content: Message content
            idempotency_key: Key for duplicate detection
            metadata: Additional metadata

        Returns:
            NotificationResult with final status
        """
        config = self._channels.get(channel)
        if not config or not config.enabled:
            result = NotificationResult(
                notification_id=str(uuid.uuid4()),
                idempotency_key=idempotency_key or str(uuid.uuid4()),
                channel=channel,
                status=DeliveryStatus.FAILED_PERMANENT,
                recipient=recipient,
                error_message=f"Channel {channel.value} not available",
            )
            self._results.append(result)
            return result

        # Generate idempotency key if not provided
        if not idempotency_key:
            key_data = (
                f"{channel.value}:{recipient}:{content}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            )
            idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()[:16]

        metadata = metadata or {}
        metadata["idempotency_key"] = idempotency_key

        # Attempt delivery with retries
        result = await self._attempt_with_retry(config, recipient, content, metadata)

        # Handle escalation if needed
        if result.is_failed():
            await self._escalate(result)

        self._results.append(result)
        return result

    async def _attempt_with_retry(
        self,
        config: ChannelConfig,
        recipient: str,
        content: str,
        metadata: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> NotificationResult:
        """Attempt delivery with retry logic"""
        last_result = None

        for attempt in range(config.max_retries + 1):
            result = await config.handler.send(recipient, content, metadata)
            last_result = result

            if result.is_success():
                return result

            if not result.can_retry() and result.status != DeliveryStatus.RETRYING:
                # Permanent failure or cannot retry
                return result

            # Calculate retry delay
            if attempt < config.max_retries:
                delay = config.retry_delays[min(attempt, len(config.retry_delays) - 1)]
                result.status = DeliveryStatus.RETRYING
                result.retry_count = attempt + 1
                await self._sleep(delay)

        # All retries exhausted
        if last_result:
            last_result.status = DeliveryStatus.FAILED_PERMANENT
            last_result.error_message = f"All {config.max_retries} retries exhausted"

        return last_result or NotificationResult(
            notification_id=str(uuid.uuid4()),
            idempotency_key=metadata.get("idempotency_key", ""),
            channel=config.channel,
            status=DeliveryStatus.FAILED_PERMANENT,
            recipient=recipient,
            error_message="All retries exhausted",
        )

    async def _escalate(self, result: NotificationResult) -> None:
        """Escalate failed notification"""
        result.status = DeliveryStatus.ESCALATED

        for handler in self._escalation_handlers:
            try:
                handler(result)
            except Exception:
                pass  # Don't let escalation failures break flow

    async def _sleep(self, seconds: float) -> None:
        """Async sleep (extracted for testability)"""
        await __import__("asyncio").sleep(seconds)

    def get_results(
        self,
        channel: NotificationChannel | None = None,
        status: DeliveryStatus | None = None,
    ) -> list[NotificationResult]:
        """Get notification results with optional filtering"""
        results = self._results

        if channel:
            results = [r for r in results if r.channel == channel]

        if status:
            results = [r for r in results if r.status == status]

        return results

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get service statistics"""
        total = len(self._results)
        if total == 0:
            return {"total": 0}

        by_channel: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        by_status: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for result in self._results:
            ch = result.channel.value
            st = result.status.value
            by_channel[ch] = by_channel.get(ch, 0) + 1
            by_status[st] = by_status.get(st, 0) + 1

        successful = sum(1 for r in self._results if r.is_success())
        failed = sum(1 for r in self._results if r.is_failed())
        escalated = sum(1 for r in self._results if r.status == DeliveryStatus.ESCALATED)

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "escalated": escalated,
            "success_rate": successful / total * 100,
            "by_channel": by_channel,
            "by_status": by_status,
        }