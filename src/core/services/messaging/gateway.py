import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class ResponseGateway:
    """
    Gateway to send messages back to various channels.
    """

    async def send_telegram_message(self, bot_token: str, chat_id: int, text: str) -> bool:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return True
                logger.error(f"Telegram API error: {response.text}")
                return False
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
                return False

    async def send_whatsapp_message(
        self, account_sid: str, auth_token: str, from_number: str, to_number: str, text: str
    ) -> bool:
        """
        Sends a WhatsApp message via Twilio.
        """
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        auth = (account_sid, auth_token)
        payload = {"From": from_number, "To": to_number, "Body": text}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=payload, auth=auth)
                if response.status_code in [200, 201]:
                    return True
                logger.error(f"Twilio API error: {response.text}")
                return False
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message: {e}")
                return False
