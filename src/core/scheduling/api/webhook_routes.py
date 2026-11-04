"""
Public webhook endpoints for Google Calendar and Microsoft Outlook.

SECURITY NOTE: These endpoints are PUBLIC (no JWT authentication) because
they are called directly by Google/Microsoft servers. Security is enforced
via:
- Header validation (Google)
- ClientState validation (Outlook)
- Channel/Subscription ID verification
- Rate limiting (IP-based)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db
from src.core.scheduling.webhooks.handlers import CalendarWebhookHandler, WebhookSecurityError

logger = logging.getLogger(__name__)

# Rate limiter for webhooks (IP-based)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/webhooks",
    tags=["Calendar Webhooks"],
)


def get_webhook_handler(db: AsyncSession = Depends(get_db)) -> CalendarWebhookHandler:
    """Dependency to get webhook handler."""
    return CalendarWebhookHandler(db, tenant_id=1)


# ========================================================================
# Google Calendar Webhooks
# ========================================================================


@router.post(
    "/google",
    status_code=200,
    summary="Receive Google Calendar push notifications",
)
@limiter.limit("100/minute")  # Rate limit: 100 requests per minute per IP
async def google_webhook(
    request: Request,  # Required by slowapi
    x_goog_channel_id: str | None = Header(None),
    x_goog_resource_id: str | None = Header(None),
    x_goog_resource_state: str | None = Header(None),
    handler: CalendarWebhookHandler = Depends(get_webhook_handler),
) -> Response:
    """
    Receive and process Google Calendar push notifications.

    Google sends webhook notifications when calendar events change.
    This endpoint validates the headers and triggers background sync.

    Headers:
    - X-Goog-Channel-ID: The channel ID from registration
    - X-Goog-Resource-ID: The resource ID being watched
    - X-Goog-Resource-State: sync/exists/not_exists

    Security:
    - Headers are validated against stored registration data
    - Invalid webhooks are silently rejected (return 200 to prevent retries)
    """
    # Validate required headers
    if not x_goog_channel_id or not x_goog_resource_id or not x_goog_resource_state:
        logger.warning("Google webhook missing required headers")
        # Return 200 to prevent Google from retrying
        return Response(status_code=200)

    try:
        await handler.handle_google_webhook(
            request=request,
            channel_id=x_goog_channel_id,
            resource_id=x_goog_resource_id,
            resource_state=x_goog_resource_state,
        )
        return Response(status_code=200)

    except WebhookSecurityError:
        logger.warning(f"Google webhook security error: channel={x_goog_channel_id}")
        # Return 200 to prevent retries, but don't process
        return Response(status_code=200)

    except Exception as exc:
        logger.exception(f"Error processing Google webhook: {exc}")
        # Return 200 to prevent retries; we logged the error
        return Response(status_code=200)


# ========================================================================
# Microsoft Outlook Webhooks
# ========================================================================


@router.post(
    "/outlook",
    status_code=200,
    summary="Receive Microsoft Graph change notifications",
)
@limiter.limit("100/minute")  # Rate limit: 100 requests per minute per IP
async def outlook_webhook(
    request: Request,  # Required by slowapi
    handler: CalendarWebhookHandler = Depends(get_webhook_handler),
) -> Response:
    """
    Receive and process Microsoft Graph change notifications.

    Microsoft sends webhook notifications when calendar events change.
    This endpoint handles both validation requests and change notifications.

    Validation Request:
    - Microsoft sends a validationToken as a query parameter
    - We must return the token in the response body with 200 OK

    Change Notification:
    - Contains subscriptionId, clientState, and change details
    - clientState is validated against stored registration
    - Background sync is triggered for valid notifications

    Security:
    - clientState is validated for all change notifications
    - Invalid notifications are silently rejected
    """
    try:
        # Parse request body
        body = await request.json()

        # Handle validation request (subscription creation)
        validation_token = body.get("validationToken")
        if validation_token:
            logger.info("Outlook webhook validation request received")
            # Return validation token in plain text with Content-Type: text/plain
            return Response(
                content=validation_token,
                media_type="text/plain",
                status_code=200,
            )

        # Handle change notifications
        change_notifications = body.get("value", [])
        if not change_notifications:
            logger.warning("Outlook webhook: no change notifications in body")
            return Response(status_code=200)

        # Process notifications
        await handler.handle_outlook_webhook(
            validation_token=None,
            change_notifications=change_notifications,
        )

        return Response(status_code=200)

    except WebhookSecurityError:
        logger.warning("Outlook webhook security error")
        return Response(status_code=200)

    except Exception as exc:
        logger.exception(f"Error processing Outlook webhook: {exc}")
        return Response(status_code=200)
