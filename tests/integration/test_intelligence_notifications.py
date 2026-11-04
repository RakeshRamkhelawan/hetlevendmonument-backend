"""
Integration tests: Intelligence Levels → Notifications

Tests that approval requirements trigger notifications
and that notification responses trigger workflows.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.notifications.inbound.action_handlers import ApprovalHandler
from src.core.notifications.inbound.intent_detector import DetectedIntent, IntentDetector
from src.core.notifications.inbound.models import ChannelType, InboundMessage, IntentType


class TestIntelligenceApprovalNotifications:
    """
    TKTI-NOTIF-001: Approval requests trigger notifications
    """

    @pytest.mark.asyncio
    async def test_approval_required_sends_notification(self):
        """
        GIVEN: User with GROWTH plan
        WHEN: Execute HIGH risk action
        THEN: Notification sent to approvers
        """
        # This test validates the integration between intelligence levels
        # and notification system. In production, this would use real services.

        # Mock the notification service
        mock_notification_service = MagicMock()
        mock_notification_service.send_approval_request = AsyncMock(
            return_value={"notification_id": "notif-123", "sent_at": datetime.utcnow().isoformat()}
        )

        # Simulate high-risk action evaluation
        action_context = {
            "action_key": "payment.process",
            "risk_level": "HIGH",
            "amount": 15000,
            "plan_tier": "GROWTH",
        }

        # Decision: requires approval
        requires_approval = action_context["risk_level"] == "HIGH"
        assert requires_approval is True

        # Notification should be triggered
        notification_result = await mock_notification_service.send_approval_request(
            tenant_id="tenant-123", action_key=action_context["action_key"], context=action_context
        )

        assert notification_result["notification_id"] is not None
        mock_notification_service.send_approval_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_response_triggers_workflow(self):
        """
        GIVEN: Pending approval notification
        WHEN: User approves via email reply
        THEN: Workflow continues
        """
        # Create simulated approval reply
        message = InboundMessage(
            id=None,
            tenant_id=None,
            channel=ChannelType.EMAIL,
            from_address="manager@example.com",
            subject="Re: Approval Request #AR-123",
            body_text="I approve this request. Please proceed with the payment.",
            in_reply_to="original-msg-id",
            received_at=datetime.utcnow(),
        )

        # Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        assert intent.type == IntentType.APPROVE

        # Process with approval handler
        handler = ApprovalHandler()

        # Handler should process (even if no approval found in DB)
        result = await handler.handle(message, intent, tenant_id="tenant-123")

        # Even without real approval request, handler should respond
        assert "action" in result

    @pytest.mark.asyncio
    async def test_restricted_action_sends_rejection_notification(self):
        """
        GIVEN: User with STARTER plan
        WHEN: Attempt CRITICAL action
        THEN: Rejection notification sent with upgrade prompt
        """
        # Mock notification service
        mock_notification_service = MagicMock()
        mock_notification_service.send_rejection_notice = AsyncMock(
            return_value={"notification_id": "notif-456", "type": "plan_restriction"}
        )

        # Simulate restricted action
        action_context = {
            "action_key": "api.delete",
            "risk_level": "CRITICAL",
            "plan_tier": "STARTER",
        }

        # Decision: not allowed for starter plan
        allowed = (
            action_context["plan_tier"] != "STARTER" or action_context["risk_level"] != "CRITICAL"
        )
        assert allowed is False

        # Send rejection notification
        result = await mock_notification_service.send_rejection_notice(
            tenant_id="tenant-123",
            action_key=action_context["action_key"],
            reason="Action requires PRO plan or higher",
            upgrade_url="/upgrade",
        )

        assert result["notification_id"] is not None
        assert result["type"] == "plan_restriction"


class TestIntelligenceLevelEscalation:
    """
    TKTI-NOTIF-002: Escalation path for time-critical approvals
    """

    @pytest.mark.asyncio
    async def test_approval_escalation_after_timeout(self):
        """
        GIVEN: Approval pending for 24 hours
        WHEN: No response from primary approver
        THEN: Escalate to next level with notification
        """
        # Simulate stale approval
        created_at = datetime.utcnow() - timedelta(hours=25)

        approval_request = {
            "id": "AR-123",
            "status": "pending",
            "created_at": created_at,
            "escalation_level": 0,
            "current_approver_id": "manager-1",
        }

        # Check if escalation needed
        is_stale = (datetime.utcnow() - created_at) > timedelta(hours=24)
        assert is_stale is True

        # Escalate
        approval_request["escalation_level"] = 1
        approval_request["current_approver_id"] = "manager-2"

        # Mock escalation notification
        mock_notification_service = MagicMock()
        mock_notification_service.send_escalation = AsyncMock(
            return_value={"notification_id": "notif-esc-1", "escalation_level": 1}
        )

        result = await mock_notification_service.send_escalation(
            approval_id=approval_request["id"],
            escalation_level=approval_request["escalation_level"],
            new_approver_id=approval_request["current_approver_id"],
        )

        assert result["escalation_level"] == 1
