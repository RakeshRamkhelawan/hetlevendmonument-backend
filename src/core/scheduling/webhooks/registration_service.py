"""
Service for registering and managing webhooks with external providers.

Handles Google Calendar watch channels and Microsoft Graph subscriptions.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.webhooks.models import WebhookRegistration
from src.core.scheduling.webhooks.repository import WebhookRepository

logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://api.sanskritisetu.org/webhooks")


class WebhookRegistrationError(Exception):
    """Raised when webhook registration fails."""

    pass


class WebhookRegistrationService:
    """
    Service for registering webhooks with Google Calendar and Microsoft Outlook.

    Handles:
    - Google Calendar watch channel creation/renewal
    - Microsoft Graph subscription creation/renewal
    - Secure clientState generation for Outlook
    """

    def __init__(self, db: AsyncSession, tenant_id: int = 1) -> None:
        self.db = db
        self.webhook_repo = WebhookRepository(db, tenant_id)
        self.integration_repo = CalendarIntegrationRepository(db)

    # ========================================================================
    # Google Calendar Webhook Registration
    # =======================================================================

    async def register_google_webhook(
        self,
        integration_id: str,
        access_token: str,
    ) -> WebhookRegistration:
        """
        Register a watch channel with Google Calendar API.

        Args:
            integration_id: The calendar integration ID
            access_token: Valid Google OAuth access token

        Returns:
            Created WebhookRegistration record

        Raises:
            WebhookRegistrationError: If registration fails
        """
        logger.info(f"Registering Google webhook for integration: {integration_id}")

        # Get integration details
        integration = await self.integration_repo.get_by_id_any(integration_id)
        if not integration:
            raise WebhookRegistrationError(f"Integration not found: {integration_id}")

        # Generate unique channel ID
        channel_id = secrets.token_urlsafe(32)

        # Calculate expiration (Google supports up to 30 days)
        expiration_days = 30
        expiration_date = datetime.now(timezone.utc) + timedelta(days=expiration_days)

        # Prepare channel config
        channel_config = {
            "id": channel_id,
            "type": "web_hook",
            "address": f"{WEBHOOK_BASE_URL}/google",
            "params": {
                "ttl": str(expiration_days * 24 * 60 * 60 * 1000),  # milliseconds
            },
        }

        # Call Google Calendar API
        calendar_id = integration.provider_calendar_id
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/watch"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=channel_config,
                )
                response.raise_for_status()
                data = response.json()

            # Extract resource ID from response
            resource_id = data.get("resourceId")

            if not resource_id:
                raise WebhookRegistrationError("No resourceId in Google response")

            # Deactivate any existing registrations for this integration
            existing = await self.webhook_repo.list_by_integration(integration_id)
            for reg in existing:
                if reg.provider == "google" and reg.is_active:
                    await self.webhook_repo.deactivate(reg.id)

            # Create registration record
            registration = await self.webhook_repo.create(
                integration_id=integration_id,
                provider="google",
                expiration_date=expiration_date,
                channel_id=channel_id,
                resource_id=resource_id,
            )

            logger.info(
                f"Google webhook registered: channel={channel_id}, "
                f"resource={resource_id}, expires={expiration_date}"
            )

            return registration

        except httpx.HTTPStatusError as exc:
            logger.error(f"Google webhook registration failed: {exc.response.text}")
            raise WebhookRegistrationError(f"Google API error: {exc.response.status_code}")

        except Exception as exc:
            logger.exception("Google webhook registration failed")
            raise WebhookRegistrationError(f"Registration failed: {exc}")

    async def stop_google_webhook(
        self,
        registration: WebhookRegistration,
        access_token: str,
    ) -> bool:
        """Stop a Google Calendar watch channel."""
        if not registration.channel_id or not registration.resource_id:
            logger.warning("Cannot stop Google webhook: missing channel/resource ID")
            return False

        url = "https://www.googleapis.com/calendar/v3/channels/stop"
        payload = {
            "id": registration.channel_id,
            "resourceId": registration.resource_id,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=payload,
                )
                response.raise_for_status()

            logger.info(f"Google webhook stopped: channel={registration.channel_id}")
            return True

        except httpx.HTTPStatusError as exc:
            logger.error(f"Failed to stop Google webhook: {exc.response.text}")
            return False

        except Exception as exc:
            logger.exception("Failed to stop Google webhook")
            return False

    # ========================================================================
    # Microsoft Outlook Webhook Registration
    # ========================================================================

    async def register_outlook_webhook(
        self,
        integration_id: str,
        access_token: str,
    ) -> WebhookRegistration:
        """
        Register a subscription with Microsoft Graph.

        Args:
            integration_id: The calendar integration ID
            access_token: Valid Microsoft OAuth access token

        Returns:
            Created WebhookRegistration record

        Raises:
            WebhookRegistrationError: If registration fails
        """
        logger.info(f"Registering Outlook webhook for integration: {integration_id}")

        # Get integration details
        integration = await self.integration_repo.get_by_id_any(integration_id)
        if not integration:
            raise WebhookRegistrationError(f"Integration not found: {integration_id}")

        # Generate secure clientState for validation
        client_state = secrets.token_urlsafe(32)

        # Calculate expiration (Microsoft max is 3 days for most subscriptions)
        expiration_days = 3
        expiration_date = datetime.now(timezone.utc) + timedelta(days=expiration_days)

        # Prepare subscription config
        subscription_config = {
            "changeType": "created,updated,deleted",
            "notificationUrl": f"{WEBHOOK_BASE_URL}/outlook",
            "resource": f"/me/calendars/{integration.provider_calendar_id}/events",
            "expirationDateTime": expiration_date.isoformat(),
            "clientState": client_state,
        }

        # Call Microsoft Graph API
        url = "https://graph.microsoft.com/v1.0/subscriptions"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=subscription_config,
                )
                response.raise_for_status()
                data = response.json()

            # Extract subscription ID from response
            subscription_id = data.get("id")

            if not subscription_id:
                raise WebhookRegistrationError("No subscription ID in Outlook response")

            # Deactivate any existing registrations for this integration
            existing = await self.webhook_repo.list_by_integration(integration_id)
            for reg in existing:
                if reg.provider == "outlook" and reg.is_active:
                    await self.webhook_repo.deactivate(reg.id)

            # Create registration record
            registration = await self.webhook_repo.create(
                integration_id=integration_id,
                provider="outlook",
                expiration_date=expiration_date,
                subscription_id=subscription_id,
                client_state=client_state,
            )

            logger.info(
                f"Outlook webhook registered: subscription={subscription_id}, "
                f"expires={expiration_date}"
            )

            return registration

        except httpx.HTTPStatusError as exc:
            logger.error(f"Outlook webhook registration failed: {exc.response.text}")
            raise WebhookRegistrationError(f"Microsoft Graph error: {exc.response.status_code}")

        except Exception as exc:
            logger.exception("Outlook webhook registration failed")
            raise WebhookRegistrationError(f"Registration failed: {exc}")

    async def renew_outlook_subscription(
        self,
        registration: WebhookRegistration,
        access_token: str,
    ) -> bool:
        """Renew an Outlook subscription before expiration."""
        if not registration.subscription_id:
            logger.warning("Cannot renew Outlook webhook: missing subscription ID")
            return False

        # Calculate new expiration (max 3 days)
        new_expiration = datetime.now(timezone.utc) + timedelta(days=3)

        url = f"https://graph.microsoft.com/v1.0/subscriptions/{registration.subscription_id}"
        payload = {"expirationDateTime": new_expiration.isoformat()}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=payload,
                )
                response.raise_for_status()

            # Update registration with new expiration
            registration.expiration_date = new_expiration
            await self.db.flush()

            logger.info(
                f"Outlook subscription renewed: {registration.subscription_id}, "
                f"new expiration: {new_expiration}"
            )
            return True

        except httpx.HTTPStatusError as exc:
            logger.error(f"Failed to renew Outlook subscription: {exc.response.text}")
            return False

        except Exception as exc:
            logger.exception("Failed to renew Outlook subscription")
            return False

    async def delete_outlook_subscription(
        self,
        registration: WebhookRegistration,
        access_token: str,
    ) -> bool:
        """Delete an Outlook subscription."""
        if not registration.subscription_id:
            logger.warning("Cannot delete Outlook webhook: missing subscription ID")
            return False

        url = f"https://graph.microsoft.com/v1.0/subscriptions/{registration.subscription_id}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()

            logger.info(f"Outlook subscription deleted: {registration.subscription_id}")
            return True

        except httpx.HTTPStatusError as exc:
            logger.error(f"Failed to delete Outlook subscription: {exc.response.text}")
            return False

        except Exception as exc:
            logger.exception("Failed to delete Outlook subscription")
            return False

    # ========================================================================
    # Refresh Expiring Webhooks
    # ========================================================================

    async def refresh_expiring_webhooks(
        self,
        hours_before: int = 24,
    ) -> dict[str, int]:
        """
        Refresh all webhooks expiring within the specified hours.

        Returns:
            Dict with counts: {"refreshed": int, "failed": int, "total": int}
        """
        expiring = await self.webhook_repo.list_expiring(hours=hours_before)

        refreshed = 0
        failed = 0

        for registration in expiring:
            try:
                # Get access token for the integration
                integration = await self.integration_repo.get_by_id_any(registration.integration_id)
                if not integration:
                    logger.warning(f"Integration not found for webhook: {registration.id}")
                    continue

                access_token = self.integration_repo.decrypt_access_token(integration)

                if registration.provider == "google":
                    # Google doesn't support renewal; stop and re-register
                    await self.stop_google_webhook(registration, access_token)
                    await self.register_google_webhook(registration.integration_id, access_token)
                    refreshed += 1

                elif registration.provider == "outlook":
                    if await self.renew_outlook_subscription(registration, access_token):
                        refreshed += 1
                    else:
                        failed += 1

            except Exception as exc:
                logger.error(f"Failed to refresh webhook {registration.id}: {exc}")
                failed += 1

        return {
            "refreshed": refreshed,
            "failed": failed,
            "total": len(expiring),
        }
