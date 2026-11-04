"""
Notification Abstraction

Multi-channel notificatie service met:
- Channel abstraction (email, SMS, WhatsApp, internal)
- Provider fallback
- Idempotency
- Status tracking
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Union
from collections.abc import Callable

from src.core.connectors.provider import ProviderCapability, ProviderResult
from src.core.connectors.resolver import ProviderResolver, ResolutionResult

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Ondersteunde notificatie kanalen."""

    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    INTERNAL = "internal"
    WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    """Status van een notificatie."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class NotificationMessage:
    """Een notificatie bericht."""

    # Required fields (no defaults)
    message_id: str
    tenant_id: str
    channel: NotificationChannel
    recipient: str

    # Optional fields (with defaults)
    workflow_id: str | None = None
    correlation_id: str | None = None
    subject: str | None = None
    body: str = ""
    body_html: str | None = None

    # Metadata
    priority: str = "normal"  # low, normal, high, urgent
    template_id: str | None = None
    template_data: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    # Attachments
    attachments: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type

    # Options
    track_opens: bool = True
    track_clicks: bool = False

    def generate_idempotency_key(self) -> str:
        """Genereer idempotency key voor dit bericht."""
        # Hash van tenant + recipient + subject + body (truncated)
        content = f"{self.tenant_id}:{self.recipient}:{self.subject}:{self.body[:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class NotificationResult:
    """Resultaat van een notificatie poging."""

    success: bool
    message_id: str

    # Status
    status: NotificationStatus
    channel: NotificationChannel

    # Provider info
    provider_id: str | None = None
    fallback_used: bool = False

    # Response
    external_id: str | None = None  # Provider's message ID
    delivered_at: datetime | None = None

    # Errors
    error_message: str | None = None
    error_code: str | None = None
    retry_count: int = 0

    # Metadata
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert naar dictionary."""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "status": self.status.value,
            "channel": self.channel.value,
            "provider_id": self.provider_id,
            "fallback_used": self.fallback_used,
            "external_id": self.external_id,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "latency_ms": self.latency_ms,
        }


class NotificationService:
    """
    Multi-channel notificatie service.

    Features:
    - Channel abstraction
    - Provider failover
    - Idempotency
    - Status callbacks
    - Retry logic
    """

    # Mapping van kanalen naar provider capabilities
    CHANNEL_CAPABILITIES = {
        NotificationChannel.EMAIL: ProviderCapability.EMAIL_SEND,
        NotificationChannel.SMS: ProviderCapability.SMS_SEND,
        NotificationChannel.WHATSAPP: ProviderCapability.WHATSAPP_SEND,
        NotificationChannel.INTERNAL: ProviderCapability.WEBHOOK_SEND,
        NotificationChannel.WEBHOOK: ProviderCapability.WEBHOOK_SEND,
    }

    def __init__(self, resolver: ProviderResolver) -> None:
        self.resolver = resolver
        self._status_callbacks: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type
        self._sent_messages: set[Any] = set[Any]()  # Idempotency cache  # TODO(TYPE): replace Any with concrete type

    def on_status_change(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Registreer callback voor status changes."""
        self._status_callbacks.append(callback)

    async def send(
        self,
        message: NotificationMessage,
        timeout_ms: int = 30000,
        idempotent: bool = True,
    ) -> NotificationResult:
        """
        Verstuur een notificatie.

        Args:
            message: Het bericht te versturen
            timeout_ms: Timeout per provider attempt
            idempotent: Of idempotency checking toe te passen

        Returns:
            NotificationResult met resultaat
        """
        start_time = datetime.now(timezone.utc)

        result = NotificationResult(
            success=False,
            message_id=message.message_id,
            status=NotificationStatus.PENDING,
            channel=message.channel,
        )

        # Idempotency check
        if idempotent:
            idempotency_key = message.generate_idempotency_key()
            if idempotency_key in self._sent_messages:
                logger.info(f"Duplicate message detected: {message.message_id}")
                result.success = True
                result.status = NotificationStatus.SENT
                result.error_message = "Duplicate message - already sent"
                return result

        # Get capability voor dit kanaal
        capability = self.CHANNEL_CAPABILITIES.get(message.channel)
        if not capability:
            result.status = NotificationStatus.FAILED
            result.error_message = f"Unsupported channel: {message.channel.value}"
            return result

        # Build payload
        payload = self._build_payload(message)

        # Resolve en execute
        resolution = await self.resolver.resolve_and_execute(
            capability=capability,
            payload=payload,
            timeout_ms=timeout_ms,
        )

        # Process result
        if resolution.success and resolution.result:
            result.success = True
            result.status = NotificationStatus.SENT
            result.provider_id = resolution.provider_id
            result.fallback_used = resolution.fallback_used
            result.external_id = (
                resolution.result.data.get("message_id") if resolution.result.data else None
            )
            result.latency_ms = resolution.resolution_time_ms

            # Cache for idempotency
            if idempotent:
                self._sent_messages.add(message.generate_idempotency_key())

            # Notify callbacks
            self._notify_status_change(result)

        else:
            # All providers failed
            result.status = NotificationStatus.FAILED
            result.error_message = self._format_errors(resolution.attempts)
            result.retry_count = len(resolution.attempts)
            result.latency_ms = resolution.resolution_time_ms

            self._notify_status_change(result)

        return result

    async def send_batch(
        self,
        messages: list[NotificationMessage],
        timeout_ms: int = 30000,
        max_concurrent: int = 10,
    ) -> list[NotificationResult | BaseException]:
        """
        Verstuur meerdere notificaties.

        Args:
            messages: Lijst van berichten
            timeout_ms: Timeout per bericht
            max_concurrent: Max aantal parallelle requests

        Returns:
            Lijst van NotificationResult
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def send_with_limit(msg: NotificationMessage) -> NotificationResult:
            async with semaphore:
                return await self.send(msg, timeout_ms)

        tasks = [send_with_limit(msg) for msg in messages]
        results: list[NotificationResult | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        return results

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build provider payload van message."""
        payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "to": message.recipient,
            "body": message.body,
            "priority": message.priority,
            "message_id": message.message_id,
            "tenant_id": message.tenant_id,
        }

        # Channel-specific fields
        if message.channel == NotificationChannel.EMAIL:
            if message.subject is not None:
                payload["subject"] = message.subject
            if message.body_html is not None:
                payload["body_html"] = message.body_html
            payload["attachments"] = message.attachments

        elif message.channel == NotificationChannel.SMS:
            # SMS heeft geen subject
            pass

        elif message.channel == NotificationChannel.INTERNAL:
            payload["webhook_url"] = f"/internal/notifications/{message.tenant_id}"
            payload["event_type"] = "notification"

        # Add template data
        if message.template_id:
            payload["template_id"] = message.template_id
            payload["template_data"] = message.template_data

        return payload

    def _format_errors(self, attempts: list[dict[str, Any]]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format error messages van attempts."""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for attempt in attempts:
            if "error" in attempt:
                errors.append(f"{attempt.get('provider_id', 'unknown')}: {attempt['error']}")

        if errors:
            return "; ".join(errors[:3])  # Max 3 errors
        return "Unknown error"

    def _notify_status_change(self, result: NotificationResult) -> None:
        """Notify registered callbacks."""
        for callback in self._status_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(result))
                else:
                    callback(result)
            except Exception:
                logger.exception("Error in status callback")

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get service metrics."""
        return {
            "resolver_metrics": self.resolver.get_metrics(),
            "sent_messages_cache_size": len(self._sent_messages),
        }


class TemplatedNotificationService:
    """
    Notificatie service met template support.

    Laat templates renderen met variabelen.
    """

    def __init__(self, notification_service: NotificationService) -> None:
        self.service = notification_service
        self._templates: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def register_template(
        self,
        template_id: str,
        channel: NotificationChannel,
        subject_template: str | None,
        body_template: str,
    ) -> None:
        """Registreer een template."""
        self._templates[template_id] = {
            "channel": channel,
            "subject_template": subject_template,
            "body_template": body_template,
        }

    async def send_templated(
        self,
        tenant_id: str,
        template_id: str,
        recipient: str,
        template_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> NotificationResult:
        """
        Verstuur een getemplatete notificatie.

        Args:
            tenant_id: Tenant ID
            template_id: Template ID
            recipient: Ontvanger
            template_data: Data voor template rendering
            **kwargs: Additionele message opties

        Returns:
            NotificationResult
        """
        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"Unknown template: {template_id}")

        # Render template
        body = template["body_template"].format(**template_data)
        subject = None
        if template["subject_template"]:
            subject = template["subject_template"].format(**template_data)

        # Create message
        message = NotificationMessage(
            message_id=f"msg_{datetime.now(timezone.utc).timestamp()}",
            tenant_id=tenant_id,
            channel=template["channel"],
            recipient=recipient,
            subject=subject,
            body=body,
            template_id=template_id,
            template_data=template_data,
            **kwargs,
        )

        return await self.service.send(message)
