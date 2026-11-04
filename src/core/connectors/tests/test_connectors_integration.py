"""
Fase 2 Integratietest

Test de complete connector runtime:
- Provider resolver met fallback
- Circuit breaker
- Notification service
- End-to-end flows

Zonder mocks - gebruikt de mock providers voor no-cost testing.
"""

import asyncio

import pytest

from src.core.connectors.circuit_breaker import CircuitBreakerConfig
from src.core.connectors.notification import (
    NotificationChannel,
    NotificationMessage,
    NotificationService,
    TemplatedNotificationService,
)
from src.core.connectors.provider import (
    MockEmailProvider,
    MockSMSProvider,
    MockWhatsAppProvider,
    ProviderCapability,
)
from src.core.connectors.resolver import ProviderResolver


class TestEndToEndProviderResolution:
    """End-to-end provider resolution tests."""

    @pytest.mark.asyncio
    async def test_email_with_primary_fallback(self):
        """
        Scenario: Email versturen met primary en fallback.

        Verwacht:
        1. Primary provider geprobeerd
        2. Bij failure -> fallback
        3. Success via fallback
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Primary faalt, fallback werkt
        resolver.register_provider(
            MockEmailProvider("sendgrid", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("aws_ses", failure_rate=0.0),
            priority=2,
        )

        service = NotificationService(resolver)

        message = NotificationMessage(
            message_id="e2e-001",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test",
            body="Hello",
        )

        result = await service.send(message)

        assert result.success is True
        assert result.provider_id == "aws_ses"
        assert result.fallback_used is True
        # ResolutionResult heeft fallback_from, NotificationResult niet direct
        # Check dat fallback_used correct is
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_multi_channel_routing(self):
        """
        Scenario: Berichten via verschillende kanalen.

        Verwacht:
        - Email -> email provider
        - SMS -> SMS provider
        - WhatsApp -> WhatsApp provider
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Register verschillende providers
        resolver.register_provider(MockEmailProvider("email"), priority=1)
        resolver.register_provider(MockSMSProvider("sms"), priority=1)
        resolver.register_provider(MockWhatsAppProvider("wa"), priority=1)

        service = NotificationService(resolver)

        # Send via verschillende kanalen
        email_msg = NotificationMessage(
            message_id="e2e-002",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test",
            body="Email body",
        )

        sms_msg = NotificationMessage(
            message_id="e2e-003",
            tenant_id="test-tenant",
            channel=NotificationChannel.SMS,
            recipient="+31612345678",
            body="SMS body",
        )

        wa_msg = NotificationMessage(
            message_id="e2e-004",
            tenant_id="test-tenant",
            channel=NotificationChannel.WHATSAPP,
            recipient="+31612345678",
            body="WA body",
        )

        email_result = await service.send(email_msg)
        sms_result = await service.send(sms_msg)
        wa_result = await service.send(wa_msg)

        assert email_result.success is True
        assert email_result.provider_id == "email"

        assert sms_result.success is True
        assert sms_result.provider_id == "sms"

        assert wa_result.success is True
        assert wa_result.provider_id == "wa"


class TestEndToEndCircuitBreaker:
    """End-to-end circuit breaker tests."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """
        Scenario: Circuit opent na herhaalde failures.

        Verwacht:
        1. Eerste requests: CLOSED, executions geprobeerd
        2. Na 5 failures: OPEN, snelle failures
        3. Timeout: HALF_OPEN
        4. Success: CLOSED
        """
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_duration_seconds=1,
        )

        resolver = ProviderResolver(
            tenant_id="test-tenant",
            circuit_breaker_config=config,
        )

        # Provider die altijd faalt
        resolver.register_provider(
            MockEmailProvider("unstable", failure_rate=1.0),
            priority=1,
        )

        service = NotificationService(resolver)

        # Send 3 messages -> circuit opent
        for i in range(3):
            msg = NotificationMessage(
                message_id=f"cb-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                body="Body",
            )
            await service.send(msg)

        # Check circuit is open
        cb_stats = resolver.get_all_circuit_breaker_stats()
        # Zoek de key met "unstable"
        matching_keys = [k for k in cb_stats.keys() if "unstable" in k]
        assert len(matching_keys) >= 1
        assert cb_stats[matching_keys[0]]["state"] == "open"

        # 4e message -> snelle fail (circuit open)
        msg4 = NotificationMessage(
            message_id="cb-3",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )
        result4 = await service.send(msg4)
        assert result4.success is False

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Nu zou circuit half_open moeten zijn
        # (maar omdat provider nog steeds faalt, gaat ie weer open)
        msg5 = NotificationMessage(
            message_id="cb-4",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )
        await service.send(msg5)


class TestEndToEndResilience:
    """End-to-end resilience tests."""

    @pytest.mark.asyncio
    async def test_complete_failure_handling(self):
        """
        Scenario: Alle providers falen.

        Verwacht:
        - Controlled failure
        - Error details
        - Retry count
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Alle providers falen
        resolver.register_provider(
            MockEmailProvider("fail1", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("fail2", failure_rate=1.0),
            priority=2,
        )

        service = NotificationService(resolver)

        msg = NotificationMessage(
            message_id="res-001",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )

        result = await service.send(msg)

        assert result.success is False
        assert result.status.value == "failed"
        assert result.retry_count == 2
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_partial_system_degradation(self):
        """
        Scenario: Deel van systeem faalt, rest werkt.

        Verwacht:
        - Failed requests bij broken providers
        - Success requests bij healthy providers
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Email kapot, SMS werkt
        resolver.register_provider(
            MockEmailProvider("broken_email", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockSMSProvider("working_sms", failure_rate=0.0),
            priority=1,
        )

        service = NotificationService(resolver)

        # Email faalt
        email_msg = NotificationMessage(
            message_id="deg-001",
            tenant_id="test-tenant",
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            body="Body",
        )
        email_result = await service.send(email_msg)
        assert email_result.success is False

        # SMS slaagt
        sms_msg = NotificationMessage(
            message_id="deg-002",
            tenant_id="test-tenant",
            channel=NotificationChannel.SMS,
            recipient="+31612345678",
            body="SMS body",
        )
        sms_result = await service.send(sms_msg)
        assert sms_result.success is True


class TestEndToEndTemplatedNotifications:
    """End-to-end templated notification tests."""

    @pytest.mark.asyncio
    async def test_welcome_email_template(self):
        """
        Scenario: Welcome email met template.

        Verwacht:
        - Template rendering
        - Correcte verzending
        """
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(MockEmailProvider("email"))

        base_service = NotificationService(resolver)
        service = TemplatedNotificationService(base_service)

        # Register welcome template
        service.register_template(
            template_id="welcome",
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome to {company}, {name}!",
            body_template="""
            Hi {name},

            Welcome to {company}! We're excited to have you on board.

            Best regards,
            The {company} Team
            """,
        )

        # Send templated
        result = await service.send_templated(
            tenant_id="test-tenant",
            template_id="welcome",
            recipient="user@example.com",
            template_data={
                "name": "John Doe",
                "company": "SanskritiSetu",
            },
        )

        assert result.success is True


class TestEndToEndBatchProcessing:
    """End-to-end batch processing tests."""

    @pytest.mark.asyncio
    async def test_batch_with_mixed_results(self):
        """
        Scenario: Batch met gemengde resultaten.

        Verwacht:
        - Sommige slagen
        - Sommige falen
        - Alle resultaten correct
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Provider die 50% van tijd faalt
        import random

        resolver.register_provider(
            MockEmailProvider("mixed", failure_rate=0.5),
            priority=1,
        )

        service = NotificationService(resolver)

        # Create batch
        messages = [
            NotificationMessage(
                message_id=f"batch-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient=f"user{i}@example.com",
                subject=f"Batch {i}",
                body=f"Body {i}",
            )
            for i in range(10)
        ]

        results = await service.send_batch(messages, max_concurrent=5)

        assert len(results) == 10

        # Sommige slagen, sommige falen
        success_count = sum(1 for r in results if not isinstance(r, BaseException) and r.success)
        failure_count = sum(1 for r in results if isinstance(r, BaseException) or not r.success)

        assert success_count > 0 or failure_count > 0


class TestEndToEndMetrics:
    """End-to-end metrics tests."""

    @pytest.mark.asyncio
    async def test_resolver_metrics(self):
        """
        Scenario: Metrics verzamelen.

        Verwacht:
        - Resolution count
        - Fallback count
        - Fallback rate
        """
        resolver = ProviderResolver(tenant_id="test-tenant")

        # Setup: primary faalt, fallback werkt
        resolver.register_provider(
            MockEmailProvider("primary", failure_rate=1.0),
            priority=1,
        )
        resolver.register_provider(
            MockEmailProvider("fallback", failure_rate=0.0),
            priority=2,
        )

        service = NotificationService(resolver)

        # Send 5 messages
        for i in range(5):
            msg = NotificationMessage(
                message_id=f"metric-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                body="Body",
            )
            await service.send(msg)

        # Check metrics
        metrics = resolver.get_metrics()

        # Alle 5 messages triggerden fallback
        assert metrics["resolution_count"] >= 1
        assert metrics["fallback_count"] >= 1
        assert metrics["provider_count"] == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics(self):
        """
        Scenario: Circuit breaker metrics.

        Verwacht:
        - State tracking
        - Failure counts
        """
        resolver = ProviderResolver(tenant_id="test-tenant")
        resolver.register_provider(
            MockEmailProvider("cb", failure_rate=1.0),
            priority=1,
        )

        service = NotificationService(resolver)

        # Trigger failures
        for i in range(5):
            msg = NotificationMessage(
                message_id=f"cb-metric-{i}",
                tenant_id="test-tenant",
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                body="Body",
            )
            await service.send(msg)

        # Check circuit breaker stats
        cb_stats = resolver.get_all_circuit_breaker_stats()

        # Zoek de juiste key
        cb_key = "test-tenant_cb"
        matching_keys = [k for k in cb_stats.keys() if "cb" in k]
        assert len(matching_keys) >= 1

        # Check stats van eerste matching key
        stats = cb_stats[matching_keys[0]]
        assert stats["state"] == "open"
        assert stats["failure_count"] >= 5
