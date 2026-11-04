"""
Webhook module for calendar integrations.

Provides real-time synchronization via webhooks from:
- Google Calendar (push notifications)
- Microsoft Outlook (Graph change notifications)
"""

from src.core.scheduling.webhooks.models import SyncConflict, WebhookRegistration
from src.core.scheduling.webhooks.registration_service import (
    WebhookRegistrationError,
    WebhookRegistrationService,
)
from src.core.scheduling.webhooks.repository import SyncConflictRepository, WebhookRepository

__all__ = [
    "WebhookRegistration",
    "SyncConflict",
    "WebhookRepository",
    "SyncConflictRepository",
    "WebhookRegistrationService",
    "WebhookRegistrationError",
]
