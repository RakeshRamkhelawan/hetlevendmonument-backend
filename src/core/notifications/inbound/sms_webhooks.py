"""SMS webhook handlers for Twilio and MessageBird.

Receives inbound SMS messages via webhooks,
validates signatures, and processes messages.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Form, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from loguru import logger

from src.core.notifications.inbound.action_handlers import ActionRouter
from src.core.notifications.inbound.intent_detector import IntentDetector
from src.core.notifications.inbound.models import ChannelType, InboundMessage, MessageStatus

router = APIRouter(prefix="/webhooks/sms", tags=["SMS Webhooks"])


def create_inbound_message(
    channel: ChannelType,
    from_number: str,
    to_number: str,
    body: str,
    message_id: str | None = None,
    provider: str | None = None,
    media_urls: list[str] | None = None,
    raw_payload: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> InboundMessage:
    """Factory function to create InboundMessage."""
    return InboundMessage(
        id=None,  # Will be set by database
        tenant_id=None,  # Will be resolved
        channel=channel.value,
        provider=provider,
        from_address=from_number,
        subject=None,
        body_text=body,
        message_id=message_id,
        media_urls=media_urls or [],
        status=MessageStatus.UNPROCESSED,
        received_at=datetime.now(timezone.utc),
        raw_payload=raw_payload,
    )


@router.post("/twilio")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(..., description="Sender phone number (E.164 format)"),
    To: str = Form(..., description="Our Twilio number"),
    Body: str = Form(..., description="Message content"),
    MessageSid: str = Form(..., description="Unique message ID"),
    NumMedia: int = Form(0, description="Number of media attachments"),
    MediaUrl0: str | None = Form(None, description="URL of first media"),
    MediaContentType0: str | None = Form(None),
    # Twilio signature header
    x_twilio_signature: str | None = Header(None, alias="X-Twilio-Signature"),
) -> Response:
    """Handle incoming SMS from Twilio.

    Twilio sends x-www-form-urlencoded POST when an SMS is received.
    Must respond within 15 seconds with TwiML or empty 200.

    Args:
        request: FastAPI request object
        From: Sender's phone number
        To: Your Twilio phone number
        Body: Message text
        MessageSid: Unique message identifier
        NumMedia: Number of media attachments
        MediaUrl0: URL to first media file
        x_twilio_signature: Signature for validation

    Returns:
        TwiML response or empty 200
    """
    try:
        # 1. Validate webhook signature (if configured)
        if not await _validate_twilio_signature(request, x_twilio_signature):
            logger.warning(f"Invalid Twilio signature for message {MessageSid}")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # 2. Resolve tenant from phone number
        tenant_id = await _resolve_tenant_by_phone(To)
        if not tenant_id:
            logger.warning(f"No tenant found for phone number: {To}")
            # Return friendly error message
            return _twiml_response("This number is not configured. Please contact support.")

        # 3. Check if sender is opted out
        if await _is_opted_out(From, tenant_id):
            logger.info(f"Ignoring message from opted-out number: {From}")
            return Response(status_code=200)

        # 4. Create inbound message record
        media_urls = [MediaUrl0] if MediaUrl0 else []
        message = create_inbound_message(
            channel=ChannelType.SMS,
            from_number=From,
            to_number=To,
            body=Body,
            message_id=MessageSid,
            provider="twilio",
            media_urls=media_urls,
            raw_payload={
                "From": From,
                "To": To,
                "Body": Body,
                "MessageSid": MessageSid,
                "NumMedia": NumMedia,
            },
        )
        message.tenant_id = int(tenant_id)

        # TODO: Save to database
        logger.info(f"Received SMS from {From} for tenant {tenant_id}")

        # 5. Detect intent
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        logger.info(f"Detected intent: {intent.type.value} (confidence: {intent.confidence})")

        # 6. Process action
        router = ActionRouter()
        result = await router.route_and_handle(message, intent, tenant_id)

        logger.info(f"Action result: {result['action']}")

        # 7. Return TwiML response if handler provided reply
        reply_message = result.get("reply_message")
        if reply_message:
            return _twiml_response(reply_message)

        return Response(status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Twilio webhook: {e}")
        # Return 500 to trigger Twilio retry
        raise HTTPException(status_code=500, detail="Processing error")


@router.post("/messagebird")
async def messagebird_sms_webhook(
    request: Request,
    # MessageBird sends JSON payload
) -> Response:
    """Handle incoming SMS from MessageBird (EU provider).

    MessageBird sends JSON POST with message details.

    Args:
        request: FastAPI request object

    Returns:
        Empty 200 response
    """
    try:
        payload = await request.json()

        # Extract MessageBird specific fields
        message_id = payload.get("id")
        from_number = payload.get("originator")
        to_number = payload.get("recipient")
        body = payload.get("body")

        if not all([from_number, to_number, body]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Validate signature (if configured)
        signature = request.headers.get("MessageBird-Signature")
        if not await _validate_messagebird_signature(request, signature):
            logger.warning(f"Invalid MessageBird signature for message {message_id}")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Resolve tenant
        tenant_id = await _resolve_tenant_by_phone(to_number)
        if not tenant_id:
            logger.warning(f"No tenant found for MessageBird number: {to_number}")
            return Response(status_code=200)

        # Create message
        message = create_inbound_message(
            channel=ChannelType.SMS,
            from_number=from_number,
            to_number=to_number,
            body=body,
            message_id=message_id,
            provider="messagebird",
            raw_payload=payload,
        )
        message.tenant_id = int(tenant_id)

        logger.info(f"Received MessageBird SMS from {from_number}")

        # Process (same as Twilio)
        detector = IntentDetector(use_llm=False)
        intent = await detector.detect_intent(message)

        router = ActionRouter()
        await router.route_and_handle(message, intent, tenant_id)

        return Response(status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing MessageBird webhook: {e}")
        raise HTTPException(status_code=500, detail="Processing error")


async def _validate_twilio_signature(request: Request, signature: str | None) -> bool:
    """Validate Twilio webhook signature.

    Policy:
    - Production: fail closed if secret or signature is missing/invalid.
    - Development: allow if secret not configured, but log warning.
    """
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    is_production = env in {"prod", "production"}
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

    if not auth_token:
        if is_production:
            logger.error("TWILIO_AUTH_TOKEN missing in production")
            return False
        logger.warning("TWILIO_AUTH_TOKEN missing; skipping Twilio signature validation")
        return True

    if not signature:
        return False

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        form_data = await request.form()
        url = str(request.url)
        return bool(validator.validate(url, dict(form_data), signature))
    except Exception as exc:
        logger.error(f"Twilio signature validation failed: {exc}")
        return False


async def _validate_messagebird_signature(request: Request, signature: str | None) -> bool:
    """Validate MessageBird webhook signature using HMAC-SHA256.

    Policy:
    - Production: fail closed if secret or signature is missing/invalid.
    - Development: allow if secret not configured, but log warning.
    """
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    is_production = env in {"prod", "production"}
    signing_secret = os.getenv("MESSAGEBIRD_WEBHOOK_SECRET", "").strip()

    if not signing_secret:
        if is_production:
            logger.error("MESSAGEBIRD_WEBHOOK_SECRET missing in production")
            return False
        logger.warning(
            "MESSAGEBIRD_WEBHOOK_SECRET missing; skipping MessageBird signature validation"
        )
        return True

    if not signature:
        return False

    raw_body = await request.body()
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    )

    expected_hex = digest.hexdigest()
    expected_b64 = base64.b64encode(digest.digest()).decode("utf-8")

    return hmac.compare_digest(signature, expected_hex) or hmac.compare_digest(
        signature, expected_b64
    )


async def _resolve_tenant_by_phone(phone_number: str) -> str | None:
    """Resolve tenant ID from phone number.

    Looks up phone number configuration to find
    which tenant owns this number.

    Args:
        phone_number: The phone number (E.164 format)

    Returns:
        Tenant ID or None if not found
    """
    # TODO: Query database for phone number -> tenant mapping
    # This would look in a table like:
    # tenant_phone_numbers(phone_number, tenant_id, provider)

    # For now, return a placeholder
    # In production, this should query the database
    logger.debug(f"Resolving tenant for phone: {phone_number}")
    return None  # Placeholder


async def _is_opted_out(phone_number: str, tenant_id: str) -> bool:
    """Check if phone number has opted out.

    Args:
        phone_number: The phone number to check
        tenant_id: The tenant ID

    Returns:
        True if opted out, False otherwise
    """
    # TODO: Query contact_opt_outs table
    # SELECT * FROM contact_opt_outs
    # WHERE contact = phone_number
    # AND (tenant_id = tenant_id OR tenant_id IS NULL)
    # AND (channel = 'sms' OR channel = 'all')
    return False  # Placeholder


def _twiml_response(message: str) -> Response:
    """Generate TwiML XML response.

    Args:
        message: The message to send back

    Returns:
        XML Response with TwiML
    """
    # Escape XML special characters
    import html

    safe_message = html.escape(message)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe_message}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")