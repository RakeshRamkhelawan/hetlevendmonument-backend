"""
Alert Notification Bridge

Connects the observability AlertManager to the real NotificationService
so that firing alerts result in actual notifications (email, webhook).

All notification sends are wrapped in best_effort so alert delivery
never crashes alert evaluation.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Any, Optional

from src.core.connectors.notification import NotificationChannel as ConnectorChannel
from src.core.connectors.notification import NotificationMessage, NotificationService
from src.core.observability.alert_manager import (
    Alert,
    AlertManager,
    AlertSeverity,
)
from src.core.observability.alert_manager import NotificationChannel as AlertChannel
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class AlertNotificationBridge:
    """Bridge that wires AlertManager channels to NotificationService channels.

    Usage:
        bridge = AlertNotificationBridge(alert_manager, notification_service)
        # Handlers are registered automatically on init
    """

    # Map AlertManager channels to NotificationService channels
    _CHANNEL_MAP: dict[AlertChannel, ConnectorChannel] = {
        AlertChannel.EMAIL: ConnectorChannel.EMAIL,
        AlertChannel.WEBHOOK: ConnectorChannel.WEBHOOK,
    }

    def __init__(
        self,
        alert_manager: AlertManager,
        notification_service: NotificationService,
    ) -> None:
        self._alert_manager = alert_manager
        self._notification = notification_service

        # Capture event loop at initialization time (app startup is async)
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        # Register handlers for supported channels
        for alert_channel, connector_channel in self._CHANNEL_MAP.items():
            alert_manager.register_handler(
                alert_channel,
                self._make_handler(connector_channel),
            )

    def _make_handler(
        self,
        connector_channel: ConnectorChannel,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Create a synchronous handler that schedules async notification send."""

        def handler(alert: Alert) -> None:
            self._schedule_notification(alert, connector_channel)

        return handler

    def _schedule_notification(
        self,
        alert: Alert,
        channel: ConnectorChannel,
    ) -> None:
        """Schedule async notification send in the captured event loop."""
        if self._loop is None:
            logger.warning("No event loop captured - cannot send alert notification")
            return

        priority = "normal"
        if alert.severity == AlertSeverity.CRITICAL:
            priority = "urgent"
        elif alert.severity == AlertSeverity.ERROR:
            priority = "high"

        message = NotificationMessage(
            message_id=alert.id,
            tenant_id=str(alert.tenant_id) if alert.tenant_id else "0",
            channel=channel,
            recipient="admin",
            subject=f"[{alert.severity.value.upper()}] {alert.name}",
            body=alert.message,
            priority=priority,
        )

        async def _do_send() -> None:
            async with best_effort("alert notification"):
                await self._notification.send(message)

        self._loop.create_task(_do_send())
