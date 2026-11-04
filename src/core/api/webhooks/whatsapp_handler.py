from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.webhooks.dependencies import WhatsAppGateway, get_db
from src.core.tasks.cva_tasks import process_cva_message

router = APIRouter()


# NOTE: tenant_id comes from the URL path -- ADR-003 exception for webhook callbacks.
# Twilio pushes to a pre-registered URL that encodes the tenant. There is no JWT in
# the inbound request from Twilio's servers. The Twilio signature is validated via
# gateway before any tenant data is accessed (see gateway.validate_signature below).
@router.post("/whatsapp/twilio/{tenant_id}")
async def twilio_whatsapp_webhook(
    tenant_id: int,
    request: Request,
    x_twilio_signature: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    form_data = await request.form()
    payload = dict(form_data)

    url = str(request.url)

    gateway = WhatsAppGateway(db=db, enqueue_fn=process_cva_message.send)

    if not await gateway.validate_signature(tenant_id, url, payload, x_twilio_signature):
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")

    await gateway.process_message(tenant_id, payload)
    await db.commit()

    return {"status": "ok"}
