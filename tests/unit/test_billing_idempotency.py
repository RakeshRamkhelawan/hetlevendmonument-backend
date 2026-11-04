# tests/unit/test_billing_idempotency.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.core.auth.dependencies import get_current_user
from src.main import create_test_app


@pytest.fixture
def test_client():
    import os

    from src.core.database.database import get_db

    with patch.dict(os.environ, {"ENABLE_SECURITY_MIDDLEWARE": "false"}):
        test_app = create_test_app()

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(test_app, raise_server_exceptions=False)
    yield client
    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stripe_webhook_idempotency_lock(test_client):
    """
    Test that a duplicate Stripe webhook event is ignored
    using the Redis two-phase idempotency lock.
    """
    from src.core.api.webhooks import stripe_handler

    # Mock stripe.Webhook.construct_event
    mock_event = {
        "id": "evt_test_12345",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_test_123",
            }
        },
    }

    # Mock redis client with two-phase lock support
    mock_redis = AsyncMock()

    # First request flow:
    # 1. set NX -> True (lock acquired)
    # 2. set processed -> True
    # Second request flow:
    # 3. set NX -> None (key exists)
    # 4. get -> "processed"
    mock_redis.set.side_effect = [True, True, None]
    mock_redis.get.side_effect = ["processed"]

    # Patch stripe.Webhook.construct_event and get_redis
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", return_value=mock_event),
        patch("src.core.api.webhooks.stripe_handler.get_redis", return_value=mock_redis),
        patch(
            "src.core.api.webhooks.stripe_handler.handle_subscription_deleted",
            AsyncMock(),
        ) as mock_deleted,
    ):

        # Send first request (should succeed)
        response1 = test_client.post(
            "/api/v1/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=mock_sig"},
            json={"dummy": "data"},
        )
        assert response1.status_code == status.HTTP_200_OK
        assert response1.json() == {"status": "success"}
        mock_deleted.assert_called_once()

        # Send second duplicate request (should return ignored status)
        response2 = test_client.post(
            "/api/v1/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=mock_sig"},
            json={"dummy": "data"},
        )
        assert response2.status_code == status.HTTP_200_OK
        assert response2.json() == {"status": "ignored"}
        # The actual handler shouldn't be called again
        mock_deleted.assert_called_once()

        # Verify redis.set was called correctly with proper key and NX parameter
        assert mock_redis.set.call_count == 3
        mock_redis.set.assert_any_call(
            "stripe_webhook_event:evt_test_12345",
            "processing",
            ex=86400,
            nx=True,
        )


@pytest.mark.asyncio
async def test_stripe_webhook_fail_closed_on_redis_down(test_client):
    """
    Test that the webhook returns 503 when Redis is unavailable
    to ensure fail-closed idempotency behavior.
    """
    mock_event = {
        "id": "evt_test_redis_down",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_test_123",
            }
        },
    }

    # Mock get_redis to raise an exception (Redis down)
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", return_value=mock_event),
        patch(
            "src.core.api.webhooks.stripe_handler.get_redis",
            side_effect=ConnectionError("Redis is down"),
        ),
    ):
        response = test_client.post(
            "/api/v1/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=mock_sig"},
            json={"dummy": "data"},
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
