"""
Unit tests for webhook handlers (telegram, whatsapp, stripe).

Covers: signature validation, payload parsing, error responses,
and proper message queuing to Dramatiq.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ============================================================================
# Telegram Webhook Tests
# ============================================================================


class TestTelegramWebhook:
    """Tests for POST /telegram/{tenant_id}/{bot_token}."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up FastAPI test app with telegram router."""
        from src.core.api.webhooks.telegram_handler import router

        self.app = FastAPI()
        self.app.include_router(router)

        # Override get_db dependency
        async def mock_db():
            yield AsyncMock()

        from src.core.database.database import get_db

        self.app.dependency_overrides[get_db] = mock_db
        self.client = TestClient(self.app)

    def test_rejects_missing_secret_token(self):
        """Request without X-Telegram-Bot-Api-Secret-Token should be rejected."""
        with patch("src.core.api.webhooks.telegram_handler.TelegramGateway") as MockGW:
            instance = AsyncMock()
            instance.validate_token.return_value = False
            MockGW.return_value = instance

            response = self.client.post(
                "/telegram/1/bot123",
                json={"message": {"text": "hello", "from": {"id": 1}, "chat": {"id": 1}}},
            )

        assert response.status_code == 401

    def test_accepts_valid_token(self):
        """Request with valid secret token should succeed."""
        with patch("src.core.api.webhooks.telegram_handler.TelegramGateway") as MockGW:
            instance = AsyncMock()
            instance.validate_token.return_value = True
            instance.process_message.return_value = None
            MockGW.return_value = instance

            response = self.client.post(
                "/telegram/1/bot123",
                json={"message": {"text": "hello", "from": {"id": 1}, "chat": {"id": 1}}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "valid_token"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_rejects_malformed_json(self):
        """Non-JSON body should return 400."""
        with patch("src.core.api.webhooks.telegram_handler.TelegramGateway") as MockGW:
            instance = AsyncMock()
            instance.validate_token.return_value = True
            MockGW.return_value = instance

            response = self.client.post(
                "/telegram/1/bot123",
                content=b"not json",
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "valid",
                },
            )

        # Should return 400 or 422 for malformed JSON
        assert response.status_code in [400, 422]


# ============================================================================
# WhatsApp/Twilio Webhook Tests
# ============================================================================


class TestWhatsAppWebhook:
    """Tests for POST /whatsapp/twilio/{tenant_id}."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.core.api.webhooks.whatsapp_handler import router

        self.app = FastAPI()
        self.app.include_router(router)

        async def mock_db():
            yield AsyncMock()

        from src.core.database.database import get_db

        self.app.dependency_overrides[get_db] = mock_db
        self.client = TestClient(self.app)

    def test_rejects_invalid_signature(self):
        """Request with invalid Twilio signature should be rejected."""
        with patch("src.core.api.webhooks.whatsapp_handler.WhatsAppGateway") as MockGW:
            instance = AsyncMock()
            instance.validate_signature.return_value = False
            MockGW.return_value = instance

            response = self.client.post(
                "/whatsapp/twilio/1",
                data={"From": "whatsapp:+1234", "Body": "hello", "NumMedia": "0"},
                headers={"X-Twilio-Signature": "invalid_sig"},
            )

        assert response.status_code == 401

    def test_accepts_valid_signature(self):
        """Request with valid Twilio signature should succeed."""
        with patch("src.core.api.webhooks.whatsapp_handler.WhatsAppGateway") as MockGW:
            instance = AsyncMock()
            instance.validate_signature.return_value = True
            instance.process_message.return_value = None
            MockGW.return_value = instance

            response = self.client.post(
                "/whatsapp/twilio/1",
                data={
                    "From": "whatsapp:+1234567890",
                    "Body": "Hello from WhatsApp",
                    "NumMedia": "0",
                    "MessageSid": "SM123",
                },
                headers={"X-Twilio-Signature": "valid_signature"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ============================================================================
# Stripe Webhook Tests
# ============================================================================


class TestStripeWebhook:
    """Tests for POST /webhooks/stripe."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.core.api.webhooks.stripe_handler import router
        from src.core.config.unified_config import config as unified_config

        self.app = FastAPI()
        self.app.include_router(router)

        async def mock_db():
            yield AsyncMock()

        from src.core.database.database import get_db

        self.app.dependency_overrides[get_db] = mock_db
        self.client = TestClient(self.app)
        # BE-SEC-055: de handler is fail-closed; happy-path-tests configureren
        # een test-secret (construct_event blijft per test gemockt).
        with patch.object(
            unified_config, "stripe_webhook_secret", "whsec_test_secret"
        ):
            yield

    def test_rejects_missing_signature(self):
        """Request without stripe-signature header should fail."""
        with patch("src.core.api.webhooks.stripe_handler.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.side_effect = Exception("Invalid signature")

            response = self.client.post(
                "/webhooks/stripe",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": ""},
            )

        assert response.status_code == 400

    def test_rejects_when_webhook_secret_not_configured(self):
        """BE-SEC-055: leeg webhook-secret -> 503, construct_event nooit aangeroepen.

        HMAC met een lege sleutel is publiek berekenbaar; verificatie met een
        leeg endpoint-secret is dus geen verificatie. Voor de fix ging de
        handler door naar construct_event met de lege sleutel.
        """
        from src.core.config.unified_config import config as unified_config

        with patch.object(unified_config, "stripe_webhook_secret", ""):
            with patch("src.core.api.webhooks.stripe_handler.stripe") as mock_stripe:
                response = self.client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "checkout.session.completed"}',
                    headers={"stripe-signature": "t=1,v1=forged"},
                )

        assert response.status_code == 503
        mock_stripe.Webhook.construct_event.assert_not_called()

    def test_rejects_when_webhook_secret_is_whitespace(self):
        """BE-SEC-056: whitespace-only webhook-secret -> 503, construct_event
        nooit aangeroepen. Een truthy string van spaties mag de fail-closed
        guard niet passeren."""
        from src.core.config.unified_config import config as unified_config

        with patch.object(unified_config, "stripe_webhook_secret", "   "):
            with patch("src.core.api.webhooks.stripe_handler.stripe") as mock_stripe:
                response = self.client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "checkout.session.completed"}',
                    headers={"stripe-signature": "t=1,v1=forged"},
                )

        assert response.status_code == 503
        mock_stripe.Webhook.construct_event.assert_not_called()

    def test_processes_checkout_completed(self):
        """Valid checkout.session.completed event should be processed."""
        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "tenant_1",
                    "subscription": "sub_123",
                }
            },
        }

        with patch("src.core.api.webhooks.stripe_handler.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = mock_event
            with patch(
                "src.core.api.webhooks.stripe_handler.handle_checkout_completed",
                new_callable=AsyncMock,
            ):
                response = self.client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "checkout.session.completed"}',
                    headers={"stripe-signature": "valid_sig"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_processes_subscription_deleted(self):
        """Valid customer.subscription.deleted event should be processed."""
        mock_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_456",
                }
            },
        }

        with patch("src.core.api.webhooks.stripe_handler.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = mock_event
            with patch(
                "src.core.api.webhooks.stripe_handler.handle_subscription_deleted",
                new_callable=AsyncMock,
            ):
                response = self.client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "customer.subscription.deleted"}',
                    headers={"stripe-signature": "valid_sig"},
                )

        assert response.status_code == 200
