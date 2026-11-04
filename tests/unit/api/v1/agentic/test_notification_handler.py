"""Unit tests for src/core/events/handlers/notification_handler.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.events.handlers.notification_handler import (
    NotificationChannel,
    NotificationEventHandler,
)
from src.core.events.pubsub_manager import EventType, PubSubMessage


@pytest.fixture
def handler() -> NotificationEventHandler:
    pubsub = MagicMock()
    pubsub.publish = AsyncMock()
    pubsub.subscribe = AsyncMock()
    return NotificationEventHandler(pubsub)


@pytest.mark.unit
def test_get_queue_stats_filters_by_tenant(handler: NotificationEventHandler) -> None:
    handler._notification_queue = [
        {
            "id": "n1",
            "channel": NotificationChannel.EMAIL.value,
            "recipient": "a@example.com",
            "subject": None,
            "title": None,
            "body": None,
            "data": {},
            "tenant_id": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "queued",
        },
        {
            "id": "n2",
            "channel": NotificationChannel.EMAIL.value,
            "recipient": "b@example.com",
            "subject": None,
            "title": None,
            "body": None,
            "data": {},
            "tenant_id": 2,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "sent",
        },
    ]
    stats = handler.get_queue_stats(tenant_id=1)
    assert stats["total"] == 1
    assert stats["queued"] == 1
    assert stats["sent"] == 0


@pytest.mark.unit
def test_get_queue_stats_without_tenant_returns_all(handler: NotificationEventHandler) -> None:
    handler._notification_queue = [
        {
            "id": "n1",
            "channel": NotificationChannel.EMAIL.value,
            "recipient": "a@example.com",
            "subject": None,
            "title": None,
            "body": None,
            "data": {},
            "tenant_id": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "queued",
        },
        {
            "id": "n2",
            "channel": NotificationChannel.EMAIL.value,
            "recipient": "b@example.com",
            "subject": None,
            "title": None,
            "body": None,
            "data": {},
            "tenant_id": 2,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "sent",
        },
    ]
    stats = handler.get_queue_stats()
    assert stats["total"] == 2
    assert stats["queued"] == 1
    assert stats["sent"] == 1


@pytest.mark.asyncio
async def test_on_user_login_does_not_log_email(handler: NotificationEventHandler, caplog: pytest.LogCaptureFixture) -> None:
    """PII such as email/user_id must not appear in INFO logs."""
    import logging

    caplog.set_level(logging.INFO)
    message = PubSubMessage(
        event_type=EventType.USER_LOGGED_IN,
        data={"user_id": "user-123", "email": "secret@example.com", "is_first_login": True},
        source="test",
        tenant_id=1,
    )
    await handler.on_user_login(message)
    info_logs = " ".join(record.message for record in caplog.records if record.levelno == logging.INFO)
    assert "secret@example.com" not in info_logs
    assert "user-123" not in info_logs


@pytest.mark.asyncio
async def test_on_system_alert_redacts_message_in_user_activity(handler: NotificationEventHandler) -> None:
    """Raw alert_message must not be forwarded unredacted to USER_ACTIVITY subscribers."""
    message = PubSubMessage(
        event_type=EventType.SYSTEM_ALERT,
        data={"level": "error", "message": "Sensitive stack trace: user password is xyz"},
        source="test",
        tenant_id=1,
    )
    await handler.on_system_alert(message)

    publish_call = handler.pubsub.publish.call_args
    assert publish_call is not None
    published_data = publish_call.kwargs["data"]
    assert published_data["message"] == "<redacted>"
    assert "Sensitive stack trace" not in published_data["message"]
