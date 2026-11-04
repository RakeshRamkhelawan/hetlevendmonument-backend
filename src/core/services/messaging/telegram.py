import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TelegramGateway:
    def __init__(self, db: AsyncSession, enqueue_fn: Callable[..., Any]) -> None:
        self.db = db
        self._enqueue = enqueue_fn

    async def validate_token(
        self, tenant_id: int, bot_token: str, secret_token: str | None
    ) -> bool:
        """
        Validate the incoming webhook request.
        Validates the X-Telegram-Bot-Api-Secret-Token to ensure the request is from Telegram.
        """
        if not secret_token:
            return False

        import os

        # PRODUCTION: Fetch the expected secret token for this tenant/bot
        expected_token = os.getenv("TELEGRAM_BOT_SECRET_TOKEN")

        if not expected_token:
            logger.error("Telegram secret token not configured for tenant %s", tenant_id)
            return False

        return secret_token == expected_token

    async def process_message(
        self,
        tenant_id: int,
        bot_token: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Process incoming Telegram webhook payload.
        Converts it to an AgentRequest and queues it in Dramatiq.
        """
        message = payload.get("message", {})
        if not message:
            logger.warning("Received Telegram payload without message")
            return

        text = message.get("text")
        if not text:
            logger.warning("Received Telegram message without text")
            return

        sender = message.get("from", {})
        chat = message.get("chat", {})

        agent_request = {
            "tenant_id": tenant_id,
            "channel": "telegram",
            "bot_token": bot_token,
            "message_id": message.get("message_id"),
            "text": text,
            "sender_id": sender.get("id"),
            "chat_id": chat.get("id"),
            # NOTE: sender.get("id") is a Telegram user ID -- PII (GDPR Recital 30).
            # Stored in Conversation.user_id; falls within DSAR/erasure scope.
            # CVA task falls back to external-user sentinel (0) if absent.
            "user_id": sender.get("id"),
        }

        # Enqueue to Dramatiq via injected callable (ADR-034 SDP: messaging -> tasks verboden)
        self._enqueue(agent_request)
        logger.info(
            "Queued Telegram message %s for tenant %s",
            message.get("message_id"),
            tenant_id,
        )
