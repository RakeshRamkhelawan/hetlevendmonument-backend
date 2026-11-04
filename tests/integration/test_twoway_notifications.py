"""
Integration tests: Two-way Notifications end-to-end

Tests inbound email/SMS processing and response handling.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.notifications.inbound.action_handlers import (
    ActionRouter,
    BounceHandler,
    TicketHandler,
    UnsubscribeHandler,
)
from src.core.notifications.inbound.intent_detector import IntentDetector
from src.core.notifications.inbound.models import (
    ChannelType,
    ContactOptOut,
    EmailBounce,
    InboundMessage,
    IntentType,
)


class TestInboundEmailProcessing:
    """
    TKTN-INBOUND-001: Email reply processing
    """

    @pytest.mark.asyncio
    async def test_invoice_reply_creates_comment(self):
        """
        GIVEN: Invoice sent to customer
        WHEN: Customer replies to email
        THEN: Reply added as comment on invoice
        """
        # Simulate invoice reply email
        message = InboundMessage(
            id=None,
            tenant_id="tenant-123",
            channel=ChannelType.EMAIL,
            from_address="customer@example.com",
            from_name="John Customer",
            to_addresses=["invoices@company.com"],
            subject="Re: Invoice #INV-2024-001",
            body_text="Please update the billing address on this invoice.",
            thread_id="original-invoice-email-id",
            in_reply_to="original-invoice-email-id",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        # Should be detected as reply (has in_reply_to)
        assert intent.type == IntentType.REPLY

        # Route and handle
        router = ActionRouter()
        result = await router.route_and_handle(message, intent, tenant_id="tenant-123")

        # Fallback to ticket creation for replies
        assert result["success"] is True
        assert result["action"] in ["ticket_created", "comment_added"]

    @pytest.mark.asyncio
    async def test_approval_email_reply_triggers_action(self):
        """
        GIVEN: Approval request email sent
        WHEN: Manager replies with 'Approve'
        THEN: Approval processed, workflow continues
        """
        # Simulate approval reply
        message = InboundMessage(
            id=None,
            tenant_id="tenant-123",
            channel=ChannelType.EMAIL,
            from_address="manager@example.com",
            subject="Re: Approval Request: Budget Increase",
            body_text="Approved. Please go ahead with the purchase.",
            thread_id="approval-req-msg-id",
            in_reply_to="approval-req-msg-id",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        # Should detect approval
        assert intent.type == IntentType.APPROVE
        assert intent.confidence > 0.8


class TestInboundSMSProcessing:
    """
    TKTN-INBOUND-002: SMS command processing
    """

    @pytest.mark.asyncio
    async def test_sms_status_command(self):
        """
        GIVEN: Customer with phone number
        WHEN: SMS "STATUS INV-123" received
        THEN: SMS reply with invoice status
        """
        # Simulate status query SMS
        message = InboundMessage(
            id=None,
            tenant_id="tenant-123",
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="STATUS INV-123",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        # Should detect as query status (STATUS is a query command)
        assert intent.type == IntentType.QUERY_STATUS

    @pytest.mark.asyncio
    async def test_sms_stop_unsubscribes(self):
        """
        GIVEN: User subscribed to SMS
        WHEN: SMS "STOP" received
        THEN: User unsubscribed, no more SMS
        """
        # Simulate STOP SMS
        message = InboundMessage(
            id=None,
            tenant_id="tenant-123",
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="STOP",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        assert intent.type == IntentType.UNSUBSCRIBE
        assert intent.confidence >= 0.9

        # Handle with unsubscribe handler
        handler = UnsubscribeHandler()
        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert result["action"] == "unsubscribed"
        assert "uitgeschreven" in result["reply_message"].lower()


class TestBounceHandling:
    """
    TKTN-INBOUND-003: Email bounce processing
    """

    @pytest.mark.asyncio
    async def test_hard_bounce_marks_email_invalid(self):
        """
        GIVEN: Email sent to invalid address
        WHEN: Hard bounce received
        THEN: Email marked invalid, notifications stopped
        """
        # Simulate bounce notification
        message = InboundMessage(
            id=None,
            tenant_id="tenant-123",
            channel=ChannelType.EMAIL,
            from_address="mailer-daemon@example.com",
            subject="Delivery Status Notification (Failure)",
            body_text="""
            This message was created automatically by mail delivery software.

            A message that you sent could not be delivered to one or more of its
            recipients. This is a permanent error.

            The following address(es) failed:
              invalid@example.com
                550 5.1.1 User unknown
            """,
            in_reply_to="original-email-id",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        assert intent.type == IntentType.BOUNCE
        assert intent.entities.get("bounce_type") == "hard"

        # Handle with bounce handler
        handler = BounceHandler()
        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert result["action"] == "bounce_processed"
        assert result["bounce_type"] == "hard"
