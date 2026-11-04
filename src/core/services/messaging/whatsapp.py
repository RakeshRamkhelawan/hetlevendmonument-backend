import hashlib
import logging
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WhatsAppGateway:
    def __init__(self, db: AsyncSession, enqueue_fn: Callable[..., Any]) -> None:
        self.db = db
        self._enqueue = enqueue_fn

    async def validate_signature(
        self,
        tenant_id: int,
        url: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        signature: str | None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Validate the incoming request from Twilio.
        """
        if not signature:
            return False

        import os

        from twilio.request_validator import RequestValidator

        # In a real multi-tenant scenario, fetch auth token from TenantIntegration table.
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        if not auth_token:
            logger.error("Twilio Auth Token not configured for tenant %s", tenant_id)
            return False

        validator = RequestValidator(auth_token)
        return cast(bool, validator.validate(url, payload, signature))

    async def process_message(
        self,
        tenant_id: int,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Process incoming Twilio WhatsApp message.
        """
        sender = payload.get("From")
        body = payload.get("Body")
        num_media = int(payload.get("NumMedia", "0"))

        if num_media > 0:
            # Hash sender before logging: phone number is PII (GDPR Recital 30).
            sender_hash = (
                hashlib.sha256(str(sender).encode()).hexdigest()[:12] if sender else "unknown"
            )
            logger.warning("Received unsupported media from sender_hash=%s", sender_hash)
            return

        if not sender or not body:
            logger.warning("Received Twilio payload without sender or body")
            return

        # TODO(SP-W02): resolve internal user_id from phone number via DB lookup:
        # user = await db.execute(select(User).where(User.phone == sender, User.tenant_id == tenant_id))
        # Until implemented, cva_tasks falls back to the external-user sentinel (0).
        # PRIVACY NOTE: DSAR erasure requests for WhatsApp users cannot be fulfilled
        # per-individual until this lookup is implemented. Track in backlog.
        user_id = None

        agent_request = {
            "tenant_id": tenant_id,
            "channel": "whatsapp_twilio",
            "message_id": payload.get("MessageSid"),
            "text": body,
            "sender_id": sender,
            "user_id": user_id,
        }

        self._enqueue(agent_request)
        logger.info(
            "Queued WhatsApp message %s for tenant %s",
            payload.get("MessageSid"),
            tenant_id,
        )
