"""
Tests voor Notification Service

Happy paths:
- Email versturen slaagt
- SMS versturen slaagt
- Provider fallback bij failure
- Batch notificaties
- Idempotency check

Unhappy paths:
- Alle providers falen
- Unsupported channel
- Timeout
"""

import asyncio

import pytest

from src.core.connectors.notification import (
    NotificationChannel,
    NotificationMessage,
    NotificationService,
    NotificationStatus,
    TemplatedNotificationService,
)
from src.core.connectors.provider import (
    MockEmailProvider,
    MockSMSProvider,
    MockWhatsAppProvider,
    ProviderCapability,
)
from src.core.connectors.resolver import ProviderResolver


class TestNotificationService:
    """Test notification service basis functionaliteit."""

    @pytest.fixture
    def email_service(self):
        """Create notification service met email providers."""
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Register providers
        resolver.register_provider(
            MockEmailProvider("sendgrid", failure_rate=0.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("aws_ses", failure_rate=0.0),
            priority=2,
        )

        return NotificationService(resolver)

    @pytest.mark.asyncio
    async def test_send_email_success(self, email_service):
        """Happy path: Email versturen slaagt."""
        message = NotificationMessage(
            message_id="msg-001",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test Subject",
            body="Test body",
        )

        result = await email_service.send(message)

        assert result.success is True
        assert result.status == NotificationStatus.SENT
        assert result.channel == NotificationChannel.EMAIL
        assert result.provider_id == "sendgrid"  # Primary
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_send_email_fallback(self):
        """Happy path: Fallback naar tweede provider."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(
            MockEmailProvider("failing", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("backup", failure_rate=0.0),
            priority=2,
        )

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="msg-002",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        result = await service.send(message)

        assert result.success is True
        assert result.provider_id == "backup"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_send_sms(self):
        """Happy path: SMS versturen."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(
            MockSMSProvider("twilio", failure_rate=0.0),
            priority=1,
        )

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="msg-003",
            tenant_id="test-tenant",
            channel=NotificationChannel.SMS,
            recipient="+31612345678",
            body="SMS body",
        )

        result = await service.send(message)

        assert result.success is True
        assert result.channel == NotificationChannel.SMS

    @pytest.mark.asyncio
    async def test_unsupported_channel(self):
        """Unhappy path: Unsupported channel."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        service = NotificationService(resolver)

        # PUSH is geregistreerd maar geen providers
        message = NotificationMessage(
            message_id="msg-004",
            tenant_id="test-tenant",
            channel=NotificationChannel.PUSH,
            recipient="device-token",
            body="Push body",
        )

        result = await service.send(message)

        assert result.success is False
        assert result.status == NotificationStatus.FAILED
        assert result.error_message is not None and "Unsupported channel" in result.error_message

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Unhappy path: Alle providers falen."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(
            MockEmailProvider("fail1", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("fail2", failure_rate=1.0),
            priority=2,
        )

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="msg-005",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        result = await service.send(message)

        assert result.success is False
        assert result.status == NotificationStatus.FAILED
        assert result.retry_count == 2


class TestNotificationIdempotency:
    """Test idempotency functionaliteit."""

    @pytest.mark.asyncio
    async def test_idempotent_send(self):
        """Happy path: Duplicate message wordt gedetecteerd."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="msg-006",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        # Eerste send
        result1 = await service.send(message, idempotent=True)
        assert result1.success is True

        # Duplicate send (zelfde content)
        message2 = NotificationMessage(
            message_id="msg-007",  # Different ID maar zelfde content
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )
        result2 = await service.send(message2, idempotent=True)

        assert result2.success is True
        assert result2.error_message is not None and "Duplicate" in result2.error_message

    @pytest.mark.asyncio
    async def test_non_idempotent_send(self):
        """Happy path: Non-idempotent laat duplicates door."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="msg-008",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        # Twee sends zonder idempotency
        result1 = await service.send(message, idempotent=False)
        result2 = await service.send(message, idempotent=False)

        assert result1.success is True
        assert result2.success is True
        assert "Duplicate" not in (result2.error_message or "")


class TestNotificationBatch:
    """Test batch notificaties."""

    @pytest.mark.asyncio
    async def test_send_batch(self):
        """Happy path: Batch notificaties versturen."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        service = NotificationService(resolver)

        messages = [
            NotificationMessage(
                message_id=f"batch-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient=f"user{i}@example.com",
                subject=f"Subject {i}",
                body=f"Body {i}",
            )
            for i in range(5)
        ]

        results = await service.send_batch(messages)

        assert len(results) == 5
        assert all(not isinstance(r, BaseException) and r.success for r in results)

    @pytest.mark.asyncio
    async def test_send_batch_with_failures(self):
        """Happy path: Batch met gedeeltelijke failures."""
        # Service die faalt
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("failing", failure_rate=1.0))

        service = NotificationService(resolver)

        messages = [
            NotificationMessage(
                message_id=f"batch-fail-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient=f"user{i}@example.com",
                subject="Test",
                body="Body",
            )
            for i in range(3)
        ]

        results = await service.send_batch(messages)

        assert len(results) == 3
        assert all(not r.success for r in results)  # type: ignore[attr-defined]


class TestNotificationCallbacks:
    """Test notification callbacks."""

    @pytest.mark.asyncio
    async def test_status_callback(self):
        """Happy path: Status callback wordt aangeroepen."""
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        service = NotificationService(resolver)

        callback_results = []

        def callback(result):
            callback_results.append(result)

        service.on_status_change(callback)

        message = NotificationMessage(
            message_id="msg-009",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        await service.send(message)

        # Callback zou aangeroepen moeten zijn
        await asyncio.sleep(0.1)  # Laat async callback lopen

        assert len(callback_results) == 1
        assert callback_results[0].success is True


class TestTemplatedNotificationService:
    """Test templated notification service."""

    @pytest.fixture
    def templated_service(self):
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        base_service = NotificationService(resolver)
        return TemplatedNotificationService(base_service)

    def test_register_template(self, templated_service):
        """Happy path: Template registratie."""
        templated_service.register_template(
            template_id="welcome_email",
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome {name}!",
            body_template="Hello {name}, welcome to {company}!",
        )

        assert "welcome_email" in templated_service._templates

    @pytest.mark.asyncio
    async def test_send_templated(self, templated_service):
        """Happy path: Templated notificatie versturen."""
        templated_service.register_template(
            template_id="welcome_email",
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome {name}!",
            body_template="Hello {name}, welcome to {company}!",
        )

        result = await templated_service.send_templated(
            tenant_id="test-tenant",
            template_id="welcome_email",
            recipient="user@example.com",
            template_data={"name": "John", "company": "Acme"},
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_unknown_template(self, templated_service):
        """Unhappy path: Onbekende template."""
        with pytest.raises(ValueError) as exc_info:
            await templated_service.send_templated(
                tenant_id="test-tenant",
                template_id="unknown_template",
                recipient="user@example.com",
                template_data={},
            )

        assert "Unknown template" in str(exc_info.value)


class TestNotificationMessage:
    """Test NotificationMessage model."""

    def test_generate_idempotency_key(self):
        """Happy path: Idempotency key generatie."""
        msg1 = NotificationMessage(
            message_id="1",
            tenant_id="tenant1",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Subject",
            body="Body",
        )

        msg2 = NotificationMessage(
            message_id="2",  # Different ID
            tenant_id="tenant1",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Subject",
            body="Body",
        )

        # Zelfde content = zelfde key
        assert msg1.generate_idempotency_key() == msg2.generate_idempotency_key()

    def test_different_content_different_key(self):
        """Happy path: Verschillende content = verschillende key."""
        msg1 = NotificationMessage(
            message_id="1",
            tenant_id="tenant1",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Subject 1",
            body="Body",
        )

        msg2 = NotificationMessage(
            message_id="2",
            tenant_id="tenant1",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Subject 2",  # Different
            body="Body",
        )

        # Verschillende content = verschillende key
        assert msg1.generate_idempotency_key() != msg2.generate_idempotency_key()
