"""Tests for action handlers."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.notifications.inbound.action_handlers import (
    ActionRouter,
    ApprovalHandler,
    BounceHandler,
    TicketHandler,
    UnsubscribeHandler,
)
from src.core.notifications.inbound.intent_detector import DetectedIntent
from src.core.notifications.inbound.models import ChannelType, InboundMessage, IntentType


class TestUnsubscribeHandler:
    """Test unsubscribe handler."""

    @pytest.mark.asyncio
    async def test_can_handle_unsubscribe(self):
        """Test handler accepts unsubscribe intent."""
        handler = UnsubscribeHandler()
        intent = DetectedIntent(type=IntentType.UNSUBSCRIBE, confidence=0.9)

        assert await handler.can_handle(intent) is True

    @pytest.mark.asyncio
    async def test_cannot_handle_other_intents(self):
        """Test handler rejects non-unsubscribe intents."""
        handler = UnsubscribeHandler()
        intent = DetectedIntent(type=IntentType.APPROVE, confidence=0.9)

        assert await handler.can_handle(intent) is False

    @pytest.mark.asyncio
    async def test_handle_sms_unsubscribe(self):
        """Test SMS unsubscribe returns Dutch message."""
        handler = UnsubscribeHandler()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="STOP",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.UNSUBSCRIBE, confidence=1.0)

        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert result["action"] == "unsubscribed"
        assert "uitgeschreven" in result["reply_message"].lower()

    @pytest.mark.asyncio
    async def test_handle_email_unsubscribe(self):
        """Test email unsubscribe returns English message."""
        handler = UnsubscribeHandler()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            body_text="unsubscribe",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.UNSUBSCRIBE, confidence=1.0)

        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert "unsubscribed" in result["reply_message"].lower()


class TestApprovalHandler:
    """Test approval handler."""

    @pytest.mark.asyncio
    async def test_can_handle_approval(self):
        """Test handler accepts approval intent."""
        handler = ApprovalHandler()
        intent = DetectedIntent(type=IntentType.APPROVE, confidence=0.9)

        assert await handler.can_handle(intent) is True

    @pytest.mark.asyncio
    async def test_can_handle_rejection(self):
        """Test handler accepts rejection intent."""
        handler = ApprovalHandler()
        intent = DetectedIntent(type=IntentType.REJECT, confidence=0.9)

        assert await handler.can_handle(intent) is True

    @pytest.mark.asyncio
    async def test_handle_approval_without_request(self):
        """Test approval when no pending request found."""
        handler = ApprovalHandler()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            body_text="I approve",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.APPROVE, confidence=0.9)

        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is False
        assert result["action"] == "approval_not_found"


class TestTicketHandler:
    """Test ticket handler (fallback)."""

    @pytest.mark.asyncio
    async def test_can_handle_any_intent(self):
        """Test handler accepts any intent as fallback."""
        handler = TicketHandler()

        assert await handler.can_handle(DetectedIntent(type=IntentType.UNKNOWN)) is True
        assert await handler.can_handle(DetectedIntent(type=IntentType.HELP)) is True

    @pytest.mark.asyncio
    async def test_handle_creates_ticket(self):
        """Test ticket creation from message."""
        handler = TicketHandler()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            subject="Help needed",
            body_text="I need assistance with my invoice.",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.UNKNOWN, confidence=0.5)

        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert result["action"] == "ticket_created"
        assert "ticket" in result["reply_message"].lower()


class TestBounceHandler:
    """Test bounce handler."""

    @pytest.mark.asyncio
    async def test_can_handle_bounce(self):
        """Test handler accepts bounce intent."""
        handler = BounceHandler()
        intent = DetectedIntent(type=IntentType.BOUNCE, confidence=0.9)

        assert await handler.can_handle(intent) is True

    @pytest.mark.asyncio
    async def test_handle_hard_bounce(self):
        """Test processing hard bounce."""
        handler = BounceHandler()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="mailer-daemon@example.com",
            subject="Delivery Status Notification (Failure)",
            body_text="The email address user@example.com does not exist.",
            in_reply_to="original-msg-id",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(
            type=IntentType.BOUNCE, confidence=0.95, entities={"bounce_type": "hard"}
        )

        result = await handler.handle(message, intent, tenant_id="tenant-123")

        assert result["success"] is True
        assert result["action"] == "bounce_processed"
        assert result["bounce_type"] == "hard"

    def test_extract_bounced_address(self):
        """Test extracting bounced address from body."""
        handler = BounceHandler()

        body = "Final-Recipient: rfc822; user@example.com\n"
        address = handler._extract_bounced_address(body)

        assert address == "user@example.com"


class TestActionRouter:
    """Test action router."""

    @pytest.mark.asyncio
    async def test_routes_to_unsubscribe_handler(self):
        """Test router sends unsubscribe to correct handler."""
        router = ActionRouter()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="STOP",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.UNSUBSCRIBE, confidence=1.0)

        result = await router.route_and_handle(message, intent, tenant_id="tenant-123")

        assert result["handler"] == "UnsubscribeHandler"
        assert result["action"] == "unsubscribed"

    @pytest.mark.asyncio
    async def test_routes_to_ticket_handler_as_fallback(self):
        """Test router uses ticket handler as fallback."""
        router = ActionRouter()

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            body_text="Random message",
            received_at=datetime.utcnow(),
        )
        intent = DetectedIntent(type=IntentType.UNKNOWN, confidence=0.5)

        result = await router.route_and_handle(message, intent, tenant_id="tenant-123")

        assert result["handler"] == "TicketHandler"
        assert result["action"] == "ticket_created"
