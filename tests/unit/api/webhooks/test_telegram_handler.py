from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.webhooks.telegram_handler import router
from src.core.database.database import get_db

app = FastAPI()
app.include_router(router, prefix="/api/v1/webhooks")


async def override_get_db():
    yield AsyncMock()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture
def valid_telegram_payload():
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {
                "id": 987654321,
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser",
            },
            "chat": {
                "id": 987654321,
                "first_name": "Test",
                "username": "testuser",
                "type": "private",
            },
            "date": 1614556800,
            "text": "Hello, bot!",
        },
    }


@patch("src.core.api.webhooks.telegram_handler.TelegramGateway.process_message")
@patch("src.core.api.webhooks.telegram_handler.TelegramGateway.validate_token")
def test_telegram_webhook_happy_path(mock_validate, mock_process, valid_telegram_payload):
    mock_validate.return_value = True
    mock_process.return_value = {"status": "ok"}

    tenant_id = 1
    bot_token = "12345:ABCDEF"
    headers = {"X-Telegram-Bot-Api-Secret-Token": "secret_token_123"}

    response = client.post(
        f"/api/v1/webhooks/telegram/{tenant_id}/{bot_token}",
        json=valid_telegram_payload,
        headers=headers,
    )

    assert response.status_code == 200
    mock_validate.assert_called_once_with(tenant_id, bot_token, "secret_token_123")
    mock_process.assert_called_once()


def test_telegram_webhook_invalid_json():
    tenant_id = 1
    bot_token = "12345:ABCDEF"
    headers = {"X-Telegram-Bot-Api-Secret-Token": "secret_token_123"}

    response = client.post(
        f"/api/v1/webhooks/telegram/{tenant_id}/{bot_token}",
        content=b"invalid json",
        headers=headers,
    )

    # Validation error for non-json data raises 422 usually in FastAPI or 400 with our manual handling.
    assert response.status_code in [400, 422]


@patch("src.core.api.webhooks.telegram_handler.TelegramGateway.validate_token")
def test_telegram_webhook_invalid_token(mock_validate, valid_telegram_payload):
    mock_validate.return_value = False

    tenant_id = 1
    bot_token = "invalid:token"
    headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}

    response = client.post(
        f"/api/v1/webhooks/telegram/{tenant_id}/{bot_token}",
        json=valid_telegram_payload,
        headers=headers,
    )

    assert response.status_code == 401
