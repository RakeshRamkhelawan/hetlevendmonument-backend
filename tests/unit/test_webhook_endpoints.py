"""Tests for inbound webhook endpoints.

HMAC-SHA256 signature is required on all inbound webhooks.
Secret is looked up via WEBHOOK_SECRET_{SOURCE} or WEBHOOK_SECRET env var.
"""
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.webhook_endpoints import router

_TEST_SECRET = "test-webhook-secret-key1"


def _sign(body: bytes, secret: str = _TEST_SECRET) -> str:
    """Generate HMAC-SHA256 signature matching the endpoint _verify_webhook_signature."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WEBHOOK_SECRET_GMAIL", _TEST_SECRET)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.unit
def test_inbound_webhook_missing_tenant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing or invalid signature returns 401."""
    client = _make_client(monkeypatch)
    resp = client.post("/webhooks/inbound/gmail", json={"event_type": "email.received"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_inbound_webhook_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid signature but malformed JSON body returns 400."""
    client = _make_client(monkeypatch)
    body = b"not-json"
    sig = _sign(body)
    resp = client.post(
        "/webhooks/inbound/gmail",
        content=body,
        headers={
            "X-Webhook-Signature": sig,
            "X-Tenant-ID": "1",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 400


@pytest.mark.unit
def test_inbound_webhook_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid signature + tenant + JSON payload returns 202 accepted."""
    client = _make_client(monkeypatch)
    body = json.dumps({"event_type": "email.received", "data": {}}).encode()
    sig = _sign(body)
    resp = client.post(
        "/webhooks/inbound/gmail",
        content=body,
        headers={
            "X-Webhook-Signature": sig,
            "X-Tenant-ID": "1",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["received"] is True
