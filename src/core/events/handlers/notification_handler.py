"""
Notification Event Handler - Processes notification events within the monolith.

Migrated from: services/notifications-service/app/main.py
Handles email, push, and in-app notifications.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import NotRequired, TypedDict

from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager

logger = logging.getLogger(__name__)


class NotificationDict(TypedDict):
    """A queued notification item."""

    id: str
    channel: str
    recipient: str
    subject: str | None
    title: str | None
    body: str | None
    data: dict[str, object]
    tenant_id: int | None
    created_at: str
    status: str
    sent_at: NotRequired[str]
    error: NotRequired[str]


class QueueStats(TypedDict):
    """Statistics for the in-memory notification queue."""

    total: int
    sent: int
    failed: int
    queued: int
    recent: list[NotificationDict]


class NotificationChannel(str, Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationEventHandler:
    """
    Handles notification-related events.

    Responsibilities:
    - Send notifications when tasks are assigned
    - Send welcome emails for new users
    - Send alerts for system events
    - Queue notifications for batch processing
    """

    def __init__(self, pubsub_manager: RedisPubSubManager) -> None:
        self.pubsub = pubsub_manager
        self.logger = logger
        # In-memory queue for notifications (would be Redis in production)
        self._notification_queue: list[NotificationDict] = []

    async def register_handlers(self) -> None:
        """Register all notification event handlers."""
        await self.pubsub.subscribe(EventType.USER_LOGGED_IN, self.on_user_login)
        await self.pubsub.subscribe(EventType.TASK_CREATED, self.on_task_assigned)
        await self.pubsub.subscribe(EventType.SYSTEM_ALERT, self.on_system_alert)
        await self.pubsub.subscribe(EventType.WORKFLOW_COMPLETED, self.on_workflow_completed)

        self.logger.info("[OK] NotificationEventHandler registered")

    async def on_user_login(self, message: PubSubMessage) -> None:
        """Send welcome notification on first login."""
        user_id = message.data.get("user_id")
        email = message.data.get("email")
        is_first_login = message.data.get("is_first_login", False)

        if is_first_login and email:
            self.logger.info("[U+0001F44B] First login event for user")

            await self._queue_notification(
                channel=NotificationChannel.EMAIL,
                recipient=email,
                subject="Welkom bij SanskritiSetu!",
                body="Welkom! Je account is nu actief.",
                tenant_id=message.tenant_id,
            )

    async def on_task_assigned(self, message: PubSubMessage) -> None:
        """
        Send notification when task is created/assigned.

        This replaces the logic from notifications-service/app/main.py
        """
        try:
            task_name = message.data.get("name", "Nieuwe taak")
            assignee = message.data.get("assignee")
            department = message.data.get("department")
            tenant_id = message.tenant_id

            if not assignee:
                self.logger.debug("No assignee for task, skipping notification")
                return

            self.logger.info("[EMAIL] Notifying assignee for task: %s", task_name)

            # Push notification
            await self._queue_notification(
                channel=NotificationChannel.PUSH,
                recipient=assignee,
                title="Nieuwe taak toegewezen",
                body=f"Je hebt een nieuwe taak: {task_name} ({department})",
                data={
                    "task_id": message.data.get("task_id"),
                    "workflow_id": message.data.get("workflow_id"),
                    "department": department,
                },
                tenant_id=tenant_id,
            )

            # In-app notification
            await self._queue_notification(
                channel=NotificationChannel.IN_APP,
                recipient=assignee,
                title="Taak toegewezen",
                body=f"{task_name}",
                data={
                    "type": "task_assigned",
                    "task_id": message.data.get("task_id"),
                },
                tenant_id=tenant_id,
            )

        except Exception:
            self.logger.exception("[FAIL] Failed to send task notification")

    async def on_system_alert(self, message: PubSubMessage) -> None:
        """Handle system alerts and send to admins."""
        try:
            level = message.data.get("level", "info")  # info, warning, error
            alert_message = message.data.get("message", "")
            tenant_id = message.tenant_id

            self.logger.info("[ALERT] System alert (%s): <redacted>", level)

            # For errors, send to admin
            if level == "error":
                await self._queue_notification(
                    channel=NotificationChannel.EMAIL,
                    recipient="admin@sanskritisetu.org",  # Configurable
                    subject="[ALERT] ERROR: System Alert",
                    body=f"Error occurred:\n\n{alert_message}\n\nTenant: {tenant_id}",
                    tenant_id=tenant_id,
                )

            # Always send in-app notification for visibility
            await self.pubsub.publish(
                event_type=EventType.USER_ACTIVITY,
                data={
                    "activity_type": "system_alert",
                    "level": level,
                    "message": "<redacted>",
                },
                tenant_id=tenant_id,
                source="notification_handler",
            )

        except Exception:
            self.logger.exception("[FAIL] Failed to handle system alert")

    async def on_workflow_completed(self, message: PubSubMessage) -> None:
        """Send notification when workflow completes."""
        workflow_id = message.data.get("workflow_id")
        user_id = message.data.get("user_id")  # Workflow initiator
        tenant_id = message.tenant_id

        if user_id:
            await self._queue_notification(
                channel=NotificationChannel.IN_APP,
                recipient=user_id,
                title="Workflow voltooid",
                body=f"Workflow {workflow_id} is succesvol afgerond.",
                data={"workflow_id": workflow_id},
                tenant_id=tenant_id,
            )

    async def _queue_notification(
        self,
        channel: NotificationChannel,
        recipient: str,
        subject: str | None = None,
        title: str | None = None,
        body: str | None = None,
        data: dict[str, object] | None = None,
        tenant_id: int | None = None,
    ) -> None:
        """
        Queue notification for processing.

        In production, this would use a background worker (Dramatiq/Celery).
        For now, we use an in-memory queue.
        """
        notification: NotificationDict = {
            "id": f"notif_{self._generate_id()}",
            "channel": channel.value,
            "recipient": recipient,
            "subject": subject,
            "title": title,
            "body": body,
            "data": data or {},
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "queued",
        }

        self._notification_queue.append(notification)
        self.logger.debug("[U+0001F4E8] Queued %s notification", channel.value)

        # Process immediately for now (would be async worker in production)
        await self._process_notification(notification)

    async def _process_notification(self, notification: NotificationDict) -> None:
        """Process a single notification."""
        channel = notification["channel"]

        try:
            if channel == NotificationChannel.EMAIL.value:
                await self._send_email(notification)
            elif channel == NotificationChannel.PUSH.value:
                await self._send_push(notification)
            elif channel == NotificationChannel.IN_APP.value:
                await self._send_in_app(notification)
            elif channel == NotificationChannel.SMS.value:
                await self._send_sms(notification)

            notification["status"] = "sent"
            notification["sent_at"] = datetime.now(timezone.utc).isoformat()

        except Exception:
            self.logger.exception("[FAIL] Failed to send %s notification", channel)
            notification["status"] = "failed"
            notification["error"] = "send failed"

    async def _send_email(self, notification: NotificationDict) -> None:
        """Send email notification."""
        # Placeholder - integrate with email service (SendGrid/AWS SES)
        self.logger.info("[EMAIL] Email notification queued")
        # TODO: Implement actual email sending

    async def _send_push(self, notification: NotificationDict) -> None:
        """Send push notification."""
        # Placeholder - integrate with push service (Firebase/OneSignal)
        self.logger.info("[PHONE] Push notification queued")
        # TODO: Implement actual push sending

    async def _send_in_app(self, notification: NotificationDict) -> None:
        """Send in-app notification via WebSocket/Redis."""
        await self.pubsub.publish(
            event_type=EventType.USER_ACTIVITY,
            data={
                "activity_type": "notification",
                "title": notification["title"],
                "body": notification["body"],
                "data": notification["data"],
            },
            tenant_id=notification.get("tenant_id"),
            source="notification_handler",
        )
        self.logger.info("[BELL] In-app notification sent")

    async def _send_sms(self, notification: NotificationDict) -> None:
        """Send SMS notification."""
        # Placeholder - integrate with SMS service (Twilio)
        self.logger.info("[MSG] SMS notification queued")
        # TODO: Implement actual SMS sending

    def _generate_id(self) -> str:
        """Generate unique ID."""
        import uuid

        return str(uuid.uuid4())[:8]

    def get_queue_stats(self, tenant_id: int | None = None) -> QueueStats:
        """Get notification queue statistics, optionally scoped to a tenant."""
        queue = (
            [n for n in self._notification_queue if n.get("tenant_id") == tenant_id]
            if tenant_id is not None
            else self._notification_queue
        )
        total = len(queue)
        sent = sum(1 for n in queue if n["status"] == "sent")
        failed = sum(1 for n in queue if n["status"] == "failed")
        queued = sum(1 for n in queue if n["status"] == "queued")

        return QueueStats(
            total=total,
            sent=sent,
            failed=failed,
            queued=queued,
            recent=queue[-10:] if queue else [],
        )
