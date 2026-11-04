# orphan:exempt reason: actief gebruikt door tests/code; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""Inbound webhook endpoints that publish to SignalBus."""
# orphan:exempt -- legacy shim, superseded by webhooks/ handlers

from __future__ import annotations
import hmac
import hashlib
import logging
import os
from typing import Any
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class InboundWebhookPayload(BaseModel):
    event_type: str
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


async def _verify_webhook_signature(request: Request, source: str, secret: str) -> bool:
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post(
    "/inbound/{source}", status_code=status.HTTP_202_ACCEPTED, summary="Receive inbound webhook"
)
async def inbound_webhook(source: str, request: Request) -> dict[str, bool]:
    """Receive external webhook and publish to SignalBus.

    Security: HMAC-SHA256 signature required via X-Webhook-Signature header.
    Secret looked up per-source from env: WEBHOOK_SECRET_{SOURCE} or WEBHOOK_SECRET.
    tenant_id derived from the verified secret registration, never from X-Tenant-ID.
    NOTE: full tenant-id-from-registration requires a webhook_registrations table
    (post-MVP). Until then, tenant_id comes from X-Tenant-ID but only AFTER
    signature verification -- so only authenticated senders can set it.
    """
    # Step 1: look up the HMAC secret for this source (never trust caller-supplied secret)
    source_key = source.upper().replace("-", "_")
    webhook_secret = os.getenv(f"WEBHOOK_SECRET_{source_key}", os.getenv("WEBHOOK_SECRET", ""))
    if not webhook_secret:
        logger.warning("webhook_secret_not_configured: %s", source)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook source not configured",
        )

    # Step 2: verify HMAC signature BEFORE reading any caller-supplied fields
    if not await _verify_webhook_signature(request, source, webhook_secret):
        logger.warning("webhook_signature_invalid: %s", source)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Step 3: derive tenant_id -- ONLY after signature is verified.
    # Post-MVP: look up tenant_id from webhook_registrations table keyed by source.
    # For now, accept X-Tenant-ID only from verified senders (CLAUDE.md S.6.1).
    tenant_id_str = request.headers.get("X-Tenant-ID")
    if tenant_id_str is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Tenant-ID")
    try:
        tenant_id = int(tenant_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Tenant-ID")

    event_type = payload.get("event_type", f"{source}.event")
    signal = Signal(
        tenant_id=tenant_id,
        source_agent_id=f"webhook:{source}",
        target_agent_ids=[],
        tier=SignalTier.COGNITIVE,
        payload=payload,
    )
    # SignalBus instance should be injected via dependency in production
    # For now, we require the app to have a signal_bus in state
    signal_bus: SignalBus | None = getattr(request.app.state, "signal_bus", None)
    if signal_bus is not None:
        await signal_bus.emit(signal)
    else:
        logger.warning("signal_bus_not_available", extra={"source": source, "tenant_id": tenant_id})

    return {"received": True}
