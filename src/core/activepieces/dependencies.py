import hashlib
import hmac
from typing import Any

from fastapi import HTTPException, Request, Security

from src.core.config.unified_config import config


async def verify_activepieces_signature(request: Request) -> None:
    """
    Validates the X-AP-Signature header against the configured webhook secret.
    """
    signature = request.headers.get("X-AP-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing signature")

    if not config.activepieces_webhook_secret:
        # If secret is not configured, we should probably fail safe or log warning
        # For this security requirement, we fail closed.
        raise HTTPException(status_code=500, detail="Webhook secret not configured on server")

    body_bytes = await request.body()

    # ActivePieces uses HMAC SHA256 (hex digest)
    expected_signature = hmac.new(
        config.activepieces_webhook_secret.encode(), body_bytes, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
