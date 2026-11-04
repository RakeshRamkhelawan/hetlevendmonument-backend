from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.webhooks.whatsapp_handler import router
from src.core.database.database import get_db

app = FastAPI()
app.include_router(router, prefix="/api/v1/webhooks")


async def override_get_db():
    yield AsyncMock()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture
def valid_twilio_payload():
    return {
        "MessageSid": "SM1234567890abcdef",
        "From": "whatsapp:+14155238886",
        "To": "whatsapp:+14155238887",
        "Body": "Hello, WhatsApp!",
        "NumMedia": "0",
    }


@patch("src.core.api.webhooks.whatsapp_handler.WhatsAppGateway.process_message")
@patch("src.core.api.webhooks.whatsapp_handler.WhatsAppGateway.validate_signature")
def test_whatsapp_webhook_happy_path(mock_validate, mock_process, valid_twilio_payload):
    mock_validate.return_value = True

    tenant_id = 1
    headers = {"X-Twilio-Signature": "valid_twilio_sig"}

    response = client.post(
        f"/api/v1/webhooks/whatsapp/twilio/{tenant_id}", data=valid_twilio_payload, headers=headers
    )

    assert response.status_code == 200
    mock_validate.assert_called_once()
    mock_process.assert_called_once()


@patch("src.core.api.webhooks.whatsapp_handler.WhatsAppGateway.validate_signature")
def test_whatsapp_webhook_invalid_signature(mock_validate, valid_twilio_payload):
    mock_validate.return_value = False

    tenant_id = 1
    headers = {"X-Twilio-Signature": "invalid_sig"}

    response = client.post(
        f"/api/v1/webhooks/whatsapp/twilio/{tenant_id}", data=valid_twilio_payload, headers=headers
    )

    assert response.status_code == 401
