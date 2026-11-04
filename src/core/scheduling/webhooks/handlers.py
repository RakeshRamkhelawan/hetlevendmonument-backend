"""
Webhook handlers for Google Calendar and Microsoft Outlook.

Implements secure webhook processing with:
- Header validation for Google webhooks
- ClientState validation for Outlook webhooks
- Automatic sync task enqueueing
"""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.webhooks.repository import WebhookRepository

logger = logging.getLogger(__name__)


class WebhookSecurityError(Exception):
    """Raised when webhook security validation fails."""

    pass


class CalendarWebhookHandler:
    """
    Handles incoming webhooks from Google Calendar and Microsoft Outlook.

    Security:
    - Google: Validates X-Goog-Channel-ID and X-Goog-Resource-ID headers
    - Outlook: Validates clientState in change notifications
    """

    def __init__(self, db: AsyncSession, tenant_id: int = 1) -> None:
        self.db = db
        self.webhook_repo = WebhookRepository(db, tenant_id)
        self.integration_repo = CalendarIntegrationRepository(db)

    # ========================================================================
    # Google Calendar Webhooks
    # =======================================================================

    async def handle_google_webhook(
        self,
        request: Request,
        channel_id: str,
        resource_id: str,
        resource_state: str,  # "sync" | "exists" | "not_exists"
    ) -> None:
        """
        Process Google Calendar push notification.

        Args:
            request: FastAPI request object for header validation
            channel_id: The channel ID from the webhook
            resource_id: The resource ID from the webhook
            resource_state: The state of the resource (sync/exists/not_exists)

        Raises:
            WebhookSecurityError: If security validation fails
        """
        logger.info(
            f"Received Google webhook: channel={channel_id}, "
            f"resource={resource_id}, state={resource_state}"
        )

        # Security validation: Verify channel_id and resource_id match headers
        if not await self._verify_google_headers(request, channel_id, resource_id):
            logger.warning(f"Google webhook security validation failed: {channel_id}")
            raise WebhookSecurityError("Invalid webhook headers")

        # Lookup webhook registration
        registration = await self.webhook_repo.get_by_channel_id(channel_id)
        if not registration or not registration.is_active:
            logger.warning(f"No active registration found for channel: {channel_id}")
            return

        # Handle different resource states
        if resource_state == "sync":
            # Sync message - webhook channel is active
            logger.info(f"Google webhook sync confirmed for channel: {channel_id}")
            return

        if resource_state == "not_exists":
            # Resource deleted or access revoked
            logger.warning(f"Google resource not exists: {resource_id}")
            # Deactivate the webhook registration
            await self.webhook_repo.deactivate(registration.id)
            return

        # resource_state == "exists" - Calendar changed, trigger sync
        await self._trigger_sync(registration.integration_id)

    async def _verify_google_headers(
        self,
        request: Request,
        channel_id: str,
        resource_id: str,
    ) -> bool:
        """
        Verify Google webhook headers match expected values.

        Google Calendar webhooks include:
        - X-Goog-Channel-ID: The channel ID (should match our stored value)
        - X-Goog-Resource-ID: The resource ID (should match our stored value)
        - X-Goog-Resource-State: sync/exists/not_exists

        Note: Google does not cryptographically sign webhooks. We rely on
        the channel_id and resource_id being unguessable for security.
        """
        headers = request.headers

        header_channel_id = headers.get("X-Goog-Channel-ID")
        header_resource_id = headers.get("X-Goog-Resource-ID")

        # Both must match exactly
        return (
            header_channel_id == channel_id
            and header_resource_id == resource_id
            and header_channel_id is not None
            and header_resource_id is not None
        )

    # ========================================================================
    # Microsoft Outlook Webhooks
    # ========================================================================

    async def handle_outlook_webhook(
        self,
        validation_token: str | None,
        change_notifications: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """
        Process Microsoft Graph change notifications.

        Args:
            validation_token: Validation token for subscription creation
            change_notifications: List of change notifications

        Returns:
            Validation token if this is a validation request, None otherwise

        Raises:
            WebhookSecurityError: If clientState validation fails
        """
        # Handle validation request (subscription creation)
        if validation_token:
            logger.info("Outlook webhook validation request received")
            return validation_token

        # Process change notifications
        logger.info(f"Received {len(change_notifications)} Outlook change notifications")

        for notification in change_notifications:
            await self._process_outlook_notification(notification)

        return None

    async def _process_outlook_notification(self, notification: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Process a single Outlook change notification."""
        subscription_id = notification.get("subscriptionId")
        client_state = notification.get("clientState")
        change_type = notification.get("changeType")  # created/updated/deleted
        resource_data = notification.get("resourceData", {})

        logger.debug(
            f"Outlook notification: subscription={subscription_id}, changeType={change_type}"
        )

        # Lookup registration by subscription ID
        if subscription_id is None:
            logger.warning("Outlook notification missing subscriptionId")
            return
        registration = await self.webhook_repo.get_by_subscription_id(str(subscription_id))
        if not registration or not registration.is_active:
            logger.warning(f"No active registration for subscription: {subscription_id}")
            return

        # Security validation: Verify clientState
        if client_state != registration.client_state:
            logger.error(
                f"Outlook webhook clientState mismatch for subscription: {subscription_id}"
            )
            raise WebhookSecurityError("Invalid clientState")

        # Trigger sync for this integration
        await self._trigger_sync(registration.integration_id)

    # ========================================================================
    # Common Sync Trigger
    # ========================================================================

    async def _trigger_sync(self, integration_id: str) -> None:
        """Enqueue a background sync task for the integration."""
        try:
            # Import here to avoid circular dependencies
            from src.workers.calendar_sync_worker import sync_calendar_integration

            # Send task to Dramatiq queue
            sync_calendar_integration.send(integration_id)

            logger.info(f"Enqueued sync task for integration: {integration_id}")

        except Exception as exc:
            logger.error(
                f"Failed to enqueue sync task for {integration_id}: {exc}",
                exc_info=True,
            )
            # Don't raise - webhook processing should not fail if queue is down
