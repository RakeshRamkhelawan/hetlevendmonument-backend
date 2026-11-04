"""Behavioral tests for AlertNotificationBridge."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.observability.alert_manager import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertStatus,
)
from src.core.observability.alert_manager import NotificationChannel as AlertChannel
from src.core.observability.alert_notification_bridge import AlertNotificationBridge


class TestAlertNotificationBridge:
    """Test that firing alerts results in notification sends."""

    @pytest.fixture
    def alert_manager(self):
        return AlertManager()

    @pytest.fixture
    def mock_notification_service(self):
        service = MagicMock()
        service.send = AsyncMock()
        return service

    def test_bridge_registers_handlers(self, alert_manager, mock_notification_service):
        """Bridge registers webhook and email handlers on AlertManager."""

        async def _init():
            return AlertNotificationBridge(alert_manager, mock_notification_service)

        loop = asyncio.new_event_loop()
        try:
            bridge = loop.run_until_complete(_init())
        finally:
            loop.close()

        assert AlertChannel.WEBHOOK in alert_manager._handlers
        assert AlertChannel.EMAIL in alert_manager._handlers

    def test_alert_fires_notification_via_webhook(self, alert_manager, mock_notification_service):
        """Critical alert triggers webhook notification send."""

        async def _init_and_fire():
            bridge = AlertNotificationBridge(alert_manager, mock_notification_service)

            from src.core.observability.alert_manager import AlertRule, AlertSeverity

            rule = AlertRule(
                name="high_error_rate",
                condition=lambda metrics: True,
                severity=AlertSeverity.CRITICAL,
                message_template="Error rate {error_rate:.2%}",
                channels=[AlertChannel.WEBHOOK],
            )
            alert_manager.register_rule(rule)

            alerts = alert_manager.evaluate_rules({"error_rate": 0.1})
            assert len(alerts) == 1

            await asyncio.sleep(0.05)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_init_and_fire())

            mock_notification_service.send.assert_called_once()
            call_args = mock_notification_service.send.call_args[0][0]
            assert call_args.channel.value == "webhook"
            assert call_args.priority == "urgent"
            assert "high_error_rate" in call_args.subject
        finally:
            loop.close()

    def test_alert_fires_notification_via_email(self, alert_manager, mock_notification_service):
        """Error alert triggers email notification send."""

        async def _init_and_fire():
            bridge = AlertNotificationBridge(alert_manager, mock_notification_service)

            from src.core.observability.alert_manager import AlertRule, AlertSeverity

            rule = AlertRule(
                name="quota_exceeded",
                condition=lambda metrics: True,
                severity=AlertSeverity.ERROR,
                message_template="Quota exceeded",
                channels=[AlertChannel.EMAIL],
            )
            alert_manager.register_rule(rule)

            alerts = alert_manager.evaluate_rules({})
            assert len(alerts) == 1
            await asyncio.sleep(0.05)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_init_and_fire())

            mock_notification_service.send.assert_called_once()
            call_args = mock_notification_service.send.call_args[0][0]
            assert call_args.channel.value == "email"
            assert call_args.priority == "high"
        finally:
            loop.close()

    def test_notification_failure_does_not_crash_alert_evaluation(
        self, alert_manager, mock_notification_service
    ):
        """Even if notification send raises, alert evaluation succeeds."""
        mock_notification_service.send = AsyncMock(side_effect=RuntimeError("Boom"))

        async def _init_and_fire():
            bridge = AlertNotificationBridge(alert_manager, mock_notification_service)

            from src.core.observability.alert_manager import AlertRule, AlertSeverity

            rule = AlertRule(
                name="test_alert",
                condition=lambda metrics: True,
                severity=AlertSeverity.WARNING,
                message_template="Test",
                channels=[AlertChannel.WEBHOOK],
            )
            alert_manager.register_rule(rule)

            alerts = alert_manager.evaluate_rules({})
            assert len(alerts) == 1
            await asyncio.sleep(0.05)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_init_and_fire())
            mock_notification_service.send.assert_called_once()
        finally:
            loop.close()

    def test_unsupported_channel_is_ignored(self, alert_manager, mock_notification_service):
        """SLACK/PAGERDUTY channels are not wired and are silently skipped."""

        async def _init_and_fire():
            bridge = AlertNotificationBridge(alert_manager, mock_notification_service)

            from src.core.observability.alert_manager import AlertRule, AlertSeverity

            rule = AlertRule(
                name="slack_only_alert",
                condition=lambda metrics: True,
                severity=AlertSeverity.INFO,
                message_template="Info",
                channels=[AlertChannel.SLACK],
            )
            alert_manager.register_rule(rule)

            alerts = alert_manager.evaluate_rules({})
            assert len(alerts) == 1
            await asyncio.sleep(0.05)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_init_and_fire())
            mock_notification_service.send.assert_not_called()
        finally:
            loop.close()
