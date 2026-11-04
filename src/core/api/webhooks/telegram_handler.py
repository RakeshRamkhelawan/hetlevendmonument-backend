import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.webhooks.dependencies import TelegramGateway, get_db
from src.core.tasks.cva_tasks import process_cva_message

logger = logging.getLogger(__name__)

router = APIRouter()


# NOTE: tenant_id comes from the URL path -- ADR-003 exception for webhook callbacks.
# Telegram pushes to a pre-registered URL that encodes the tenant. There is no JWT in
# the inbound request from Telegram's servers. The bot_token is validated via gateway
# before any tenant data is accessed (see gateway.validate_token below).
@router.post("/telegram/{tenant_id}/{bot_token}")
async def telegram_webhook(
    tenant_id: int,
    bot_token: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    gateway = TelegramGateway(db=db, enqueue_fn=process_cva_message.send)

    if not await gateway.validate_token(tenant_id, bot_token, x_telegram_bot_api_secret_token):
        logger.warning("Token validation failed for tenant %s", tenant_id)
        raise HTTPException(status_code=401, detail="Unauthorized")

    await gateway.process_message(tenant_id, bot_token, payload)
    await db.commit()

    return {"status": "ok"}
