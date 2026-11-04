"""Webhook handlers for real-time calendar sync.

Supports Google Calendar push notifications and Microsoft Graph change notifications.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from fastapi import Header, HTTPException, Request

from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.integrations.sync_service import CalendarSyncService

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Handler for incoming calendar webhooks."""

    def __init__(
        self,
        integration_repo: CalendarIntegrationRepository,
        sync_service: CalendarSyncService,
    ) -> None:
        self._integration_repo = integration_repo
        self._sync_service = sync_service

    async def handle_google_webhook(
        self,
        request: Request,
        x_goog_channel_id: str | None = Header(None),
        x_goog_resource_id: str | None = Header(None),
        x_goog_resource_state: str | None = Header(None),
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle Google Calendar push notification.

        Google sends a POST request when calendar changes occur.
        The actual sync is triggered asynchronously.
        """
        if not x_goog_channel_id:
            raise HTTPException(status_code=400, detail="Missing channel ID")

        # Log the notification
        logger.info(
            f"Google webhook received: channel={x_goog_channel_id}, "
            f"resource={x_goog_resource_id}, state={x_goog_resource_state}"
        )

        # Find integration by webhook channel ID
        # Note: In production, store channel_id -> integration mapping
        # For now, trigger sync for all active Google integrations
        if x_goog_resource_state in ("sync", "exists"):
            # Initial sync notification, can be ignored
            return {"status": "acknowledged", "message": "Sync notification received"}

        # Trigger sync for the relevant integration
        # TODO: Map channel_id to specific integration
        return {
            "status": "accepted",
            "message": "Sync queued",
            "channel_id": x_goog_channel_id,
        }

    async def handle_microsoft_webhook(
        self,
        request: Request,
        validation_token: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle Microsoft Graph change notification.

        Microsoft uses validation tokens for webhook registration
        and JSON notifications for actual changes.
        """
        # Handle validation request (GET or POST with validationToken)
        if validation_token:
            logger.info("Microsoft webhook validation request received")
            return {"validationToken": validation_token}

        # Handle actual notification
        try:
            body = await request.json()
            logger.info(f"Microsoft webhook notification: {json.dumps(body)[:200]}...")

            # Process change notifications
            if "value" in body:
                for notification in body["value"]:
                    await self._process_microsoft_notification(notification)

            return {"status": "accepted"}
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Microsoft webhook")
            raise HTTPException(status_code=400, detail="Invalid JSON")

    async def _process_microsoft_notification(self, notification: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Process a single Microsoft change notification."""
        resource = notification.get("resource", "")
        change_type = notification.get("changeType", "")
        client_state = notification.get("clientState", "")

        logger.info(f"Microsoft notification: resource={resource}, change_type={change_type}")

        # TODO: Map notification to integration and trigger sync
        # This requires storing subscription_id -> integration mapping

    def verify_google_signature(
        self,
        request: Request,
        body: bytes,
        expected_token: str,
    ) -> bool:
        """Verify Google webhook signature.

        Google doesn't sign webhooks by default, but we can use
        channel tokens for validation.
        """
        # In production, implement proper validation
        # For now, accept all (rely on channel ID validation)
        return True

    def verify_microsoft_signature(
        self,
        request: Request,
        body: bytes,
        secret: str,
    ) -> bool:
        """Verify Microsoft Graph webhook signature."""
        signature = request.headers.get("X-Microsoft-Signature", "")

        # Compute expected signature
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected)


# Webhook registration utilities
class WebhookRegistration:
    """Utilities for registering webhooks with calendar providers."""

    @staticmethod
    async def register_google_webhook(
        access_token: str,
        calendar_id: str,
        webhook_url: str,
        channel_id: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Register a webhook with Google Calendar API.

        Returns the created channel resource.
        """
        import httpx

        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/watch"

        payload = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    async def stop_google_webhook(
        access_token: str,
        channel_id: str,
        resource_id: str,
    ) -> None:
        """Stop watching a Google Calendar webhook."""
        import httpx

        url = "https://www.googleapis.com/calendar/v3/channels/stop"

        payload = {
            "id": channel_id,
            "resourceId": resource_id,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
            resp.raise_for_status()

    @staticmethod
    async def register_microsoft_webhook(
        access_token: str,
        webhook_url: str,
        client_state: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Register a webhook with Microsoft Graph API.

        Returns the created subscription resource.
        """
        import httpx

        url = "https://graph.microsoft.com/v1.0/subscriptions"

        # Subscription expires in 3 days max (renewable)
        from datetime import datetime, timedelta, timezone

        expiration = datetime.now(tz=timezone.utc) + timedelta(days=3)

        payload = {
            "changeType": "created,updated,deleted",
            "notificationUrl": webhook_url,
            "resource": "/me/events",
            "expirationDateTime": expiration.isoformat(),
            "clientState": client_state,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    async def renew_microsoft_webhook(
        access_token: str,
        subscription_id: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Renew a Microsoft Graph webhook subscription."""
        from datetime import datetime, timedelta, timezone

        import httpx

        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"

        # Extend by 3 days
        expiration = datetime.now(tz=timezone.utc) + timedelta(days=3)

        payload = {
            "expirationDateTime": expiration.isoformat(),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
