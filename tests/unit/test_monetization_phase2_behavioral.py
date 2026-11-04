# tests/unit/test_monetization_phase2_behavioral.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from src.core.api.webhooks.stripe_handler import stripe_webhook
from src.core.services.stripe_service import stripe_service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_behavioral_2_b_1_stripe_checkout_metadata():
    """
    Test 2.B.1 (Stripe Checkout Metadata):
    Verify that calling stripe_service.create_checkout_session correctly
    forwards the metadata containing tenant_id and subscription_tier to stripe.checkout.Session.create.
    """
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/mock/session/beh_cs_123"

    with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_stripe_create:
        # Patch the stripe api key in stripe_service so it does not return None
        with patch.object(stripe_service, "api_key", "sk_test_mock_123"):
            url = await stripe_service.create_checkout_session(
                customer_id="cus_beh_123",
                success_url="https://success.url",
                cancel_url="https://cancel.url",
                price_id="price_pro_monthly",
                metadata={"tenant_id": "456", "subscription_tier": "pro"},
            )

            assert url == "https://checkout.stripe.com/mock/session/beh_cs_123"
            mock_stripe_create.assert_called_once_with(
                customer="cus_beh_123",
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": "price_pro_monthly",
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url="https://success.url",
                cancel_url="https://cancel.url",
                metadata={"tenant_id": "456", "subscription_tier": "pro"},
                api_key="sk_test_mock_123",
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_behavioral_2_b_2_signature_validation():
    """
    Test 2.B.2 (Signature Validation & Integration):
    Verify that stripe_webhook raises an HTTP 400 Exception when the
    signature validation fails (i.e. stripe.Webhook.construct_event raises an exception).
    """
    # Create a mock Request
    mock_request = MagicMock()
    mock_request.body = AsyncMock(return_value=b"dummy_payload")

    # We patch stripe.Webhook.construct_event to raise a ValueError (invalid signature)
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", side_effect=ValueError("Invalid signature")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(
                request=mock_request, stripe_signature="invalid_sig", db=MagicMock()
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid signature"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_behavioral_2_b_3_idempotency_protection():
    """
    Test 2.B.3 (Idempotency Protection):
    Verify that when the same Stripe webhook event ID is received twice,
    the second request is ignored and returns status 'ignored' due to the Redis idempotency lock.
    """
    mock_request = MagicMock()
    mock_request.body = AsyncMock(return_value=b"dummy_payload")

    mock_event = {
        "id": "evt_beh_duplicate_999",
        "type": "customer.subscription.updated",
        "data": {"object": {"customer": "cus_beh_999", "status": "active"}},
    }

    mock_redis = AsyncMock()

    # Two-phase lock mock behavior:
    # 1. set NX "processing" -> True (lock acquired)
    # 2. set "processed" -> True
    # 3. set NX "processing" -> None (key exists)
    # 4. get -> "processed"
    mock_redis.set.side_effect = [True, True, None]
    mock_redis.get.side_effect = ["processed"]

    # We mock stripe.Webhook.construct_event to return the same event
    # and mock get_redis to return our mock_redis client.
    # We also mock handle_subscription_updated to avoid database execution.
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", return_value=mock_event),
        patch("src.core.api.webhooks.stripe_handler.get_redis", return_value=mock_redis),
        patch(
            "src.core.api.webhooks.stripe_handler.handle_subscription_updated", AsyncMock()
        ) as mock_handle_sub,
    ):  # noqa: E501

        # First request (lock acquired)
        response1 = await stripe_webhook(
            request=mock_request,
            stripe_signature="sig_1",
            db=MagicMock(),
        )
        assert response1 == {"status": "success"}
        mock_handle_sub.assert_called_once()

        # Reset mock call count
        mock_handle_sub.reset_mock()

        # Second request (already processed)
        response2 = await stripe_webhook(
            request=mock_request,
            stripe_signature="sig_2",
            db=MagicMock(),
        )
        assert response2 == {"status": "ignored"}
        mock_handle_sub.assert_not_called()
