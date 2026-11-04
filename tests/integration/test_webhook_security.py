import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

# Note: We will implement this dependency in the Green phase
# from src.core.activepieces.dependencies import verify_activepieces_signature


async def mock_receive():
    return {"type": "body"}


def create_request(body: dict, headers: dict):
    req = MagicMock(spec=Request)
    req.json = MagicMock(side_effect=lambda: body)

    # Make body() awaitable
    async def get_body():
        return json.dumps(body).encode()

    req.body = MagicMock(side_effect=get_body)
    req.headers = headers
    return req


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature():
    """
    Validation Test (Red Phase -> Green):
    Request without X-AP-Signature header should raise 403.
    """
    from src.core.activepieces.dependencies import verify_activepieces_signature

    # Needs secret to avoid 500 error
    with patch("src.core.activepieces.dependencies.config") as mock_config:
        mock_config.activepieces_webhook_secret = "s3cr3t"

        req = create_request({"data": "test"}, {})

        with pytest.raises(HTTPException) as exc:
            await verify_activepieces_signature(req)
        assert exc.value.status_code == 403
        assert "Missing signature" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature():
    """
    Validation Test (Red Phase -> Green):
    Request with incorrect signature should raise 403.
    """
    from src.core.activepieces.dependencies import verify_activepieces_signature

    with patch("src.core.activepieces.dependencies.config") as mock_config:
        mock_config.activepieces_webhook_secret = "s3cr3t"

        req = create_request({"data": "test"}, {"X-AP-Signature": "inv@lid"})

        with pytest.raises(HTTPException) as exc:
            await verify_activepieces_signature(req)
        assert exc.value.status_code == 403
        assert "Invalid signature" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signature():
    """
    Validation Test (Red Phase -> Green):
    Request with correct HMAC-SHA256 signature should pass.
    """
    from src.core.activepieces.dependencies import verify_activepieces_signature

    secret = "s3cr3t"
    body = {"data": "test"}
    body_bytes = json.dumps(body).encode()

    # Calculate expected signature
    signature = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

    with patch("src.core.activepieces.dependencies.config") as mock_config:
        mock_config.activepieces_webhook_secret = secret

        req = create_request(body, {"X-AP-Signature": signature})

        # Should NOT raise exception
        await verify_activepieces_signature(req)
