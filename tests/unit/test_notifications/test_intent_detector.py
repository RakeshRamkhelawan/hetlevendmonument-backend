"""Tests for intent detection."""

from datetime import datetime

import pytest

from src.core.notifications.inbound.intent_detector import DetectedIntent, IntentDetector
from src.core.notifications.inbound.models import ChannelType, InboundMessage, IntentType


class TestIntentDetector:
    """Test intent detection from inbound messages."""

    def test_detect_unsubscribe_intent(self):
        """Test detecting unsubscribe/stop commands."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="STOP",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.UNSUBSCRIBE
        assert intent.confidence > 0.8

    def test_detect_approval_intent(self):
        """Test detecting approval commands."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            subject="Re: Approval Request",
            body_text="I approve this request. Please proceed.",
            in_reply_to="original-msg-id",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.APPROVE

    def test_detect_rejection_intent(self):
        """Test detecting rejection commands."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            subject="Re: Approval Request",
            body_text="I reject this proposal.",
            in_reply_to="original-msg-id",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.REJECT

    def test_detect_reply_intent(self):
        """Test detecting reply messages."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            subject="Re: Your Invoice",
            body_text="Thanks for the invoice. I'll pay it next week.",
            in_reply_to="original-msg-id",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.REPLY

    def test_detect_bounce_intent(self):
        """Test detecting bounce messages."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="mailer-daemon@example.com",
            subject="Delivery Status Notification (Failure)",
            body_text="The email address does not exist.",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.BOUNCE
        assert intent.entities.get("bounce_type") == "hard"

    def test_detect_out_of_office_intent(self):
        """Test detecting out-of-office auto-replies."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="user@example.com",
            subject="Out of Office",
            body_text="I am currently out of the office.",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.OUT_OF_OFFICE

    def test_detect_approval_code_pattern(self):
        """Test detecting 6-character approval codes."""
        detector = IntentDetector(use_llm=False)

        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.SMS,
            from_address="+31612345678",
            body_text="ABC123",
            received_at=datetime.utcnow(),
        )

        import asyncio

        intent = asyncio.run(detector.detect_intent(message))

        assert intent.type == IntentType.COMMAND
        assert intent.entities.get("approval_code") == "ABC123"


class TestDetectedIntent:
    """Test DetectedIntent dataclass."""

    def test_high_confidence_check(self):
        """Test is_high_confidence method."""
        intent = DetectedIntent(type=IntentType.APPROVE, confidence=0.95)

        assert intent.is_high_confidence() is True
        assert intent.is_high_confidence(threshold=0.99) is False

    def test_entities_default(self):
        """Test default empty entities."""
        intent = DetectedIntent(type=IntentType.UNKNOWN)

        assert intent.entities == {}
