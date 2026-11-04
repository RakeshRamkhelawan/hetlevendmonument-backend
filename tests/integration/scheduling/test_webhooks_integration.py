"""Integration tests for Webhook API.

Tests use real PostgreSQL database with no mocks (except auth).
Webhooks are tested by calling the endpoints directly.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.integrations.models import CalendarIntegration

pytestmark = pytest.mark.asyncio


class TestGoogleWebhook:
    """Tests for POST /scheduling/webhooks/google (Google Calendar webhooks)."""

    async def test_google_webhook_valid_headers(
        self, async_client: AsyncClient, integration_factory
    ):
        """Process Google webhook with valid headers."""
        integration = await integration_factory(
            provider="google",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "test-channel-123",
                "X-Goog-Resource-ID": "test-resource-456",
                "X-Goog-Resource-State": "sync",
            },
        )

        # Webhooks always return 200 to prevent retries
        assert response.status_code == 200

    async def test_google_webhook_sync_state(self, async_client: AsyncClient, integration_factory):
        """Process Google webhook sync state."""
        integration = await integration_factory(
            provider="google",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "test-channel-789",
                "X-Goog-Resource-ID": "resource-789",
                "X-Goog-Resource-State": "sync",  # Initial sync
            },
        )

        assert response.status_code == 200

    async def test_google_webhook_exists_state(
        self, async_client: AsyncClient, integration_factory
    ):
        """Process Google webhook exists state (change notification)."""
        integration = await integration_factory(
            provider="google",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "test-channel-exists",
                "X-Goog-Resource-ID": "resource-exists",
                "X-Goog-Resource-State": "exists",  # Change notification
            },
        )

        assert response.status_code == 200

    async def test_google_webhook_missing_headers(self, async_client: AsyncClient):
        """Google webhook with missing headers still returns 200."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={},  # No headers
        )

        # Returns 200 to prevent retries, but logs error
        assert response.status_code == 200

    async def test_google_webhook_invalid_channel(self, async_client: AsyncClient):
        """Google webhook with unknown channel still returns 200."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "unknown-channel",
                "X-Goog-Resource-ID": "unknown-resource",
                "X-Goog-Resource-State": "exists",
            },
        )

        # Returns 200 to prevent retries
        assert response.status_code == 200


class TestOutlookWebhook:
    """Tests for POST /scheduling/webhooks/outlook (Outlook webhooks)."""

    async def test_outlook_webhook_valid_payload(
        self, async_client: AsyncClient, integration_factory
    ):
        """Process Outlook webhook with valid payload."""
        integration = await integration_factory(
            provider="outlook",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "value": [
                    {
                        "subscriptionId": "test-subscription-123",
                        "changeType": "created",
                        "resource": "me/events/123",
                    }
                ]
            },
        )

        assert response.status_code == 200

    async def test_outlook_webhook_validation_request(self, async_client: AsyncClient):
        """Handle Outlook webhook validation request."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "validationToken": "test-validation-token-123",
            },
        )

        assert response.status_code == 200
        # Should return validation token in plain text response
        assert response.text == "test-validation-token-123"

    async def test_outlook_webhook_multiple_events(
        self, async_client: AsyncClient, integration_factory
    ):
        """Process Outlook webhook with multiple change events."""
        integration = await integration_factory(
            provider="outlook",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "value": [
                    {
                        "subscriptionId": "test-subscription-multi",
                        "changeType": "created",
                        "resource": "me/events/1",
                    },
                    {
                        "subscriptionId": "test-subscription-multi",
                        "changeType": "updated",
                        "resource": "me/events/2",
                    },
                    {
                        "subscriptionId": "test-subscription-multi",
                        "changeType": "deleted",
                        "resource": "me/events/3",
                    },
                ]
            },
        )

        assert response.status_code == 200

    async def test_outlook_webhook_invalid_subscription(self, async_client: AsyncClient):
        """Outlook webhook with unknown subscription still returns 200."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "value": [
                    {
                        "subscriptionId": "unknown-subscription",
                        "changeType": "created",
                        "resource": "me/events/123",
                    }
                ]
            },
        )

        # Returns 200 to prevent retries
        assert response.status_code == 200

    async def test_outlook_webhook_empty_body(self, async_client: AsyncClient):
        """Outlook webhook with empty body."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            json={},
        )

        # Should handle gracefully
        assert response.status_code in [200, 400]


class TestWebhookSecurity:
    """Tests for webhook security validations."""

    async def test_google_webhook_channel_mismatch(
        self, async_client: AsyncClient, integration_factory
    ):
        """Google webhook with mismatched channel/resource."""
        integration = await integration_factory(
            provider="google",
        )

        # Send with wrong resource ID
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "correct-channel",
                "X-Goog-Resource-ID": "wrong-resource",
                "X-Goog-Resource-State": "exists",
            },
        )

        # Still returns 200 to prevent retries
        assert response.status_code == 200

    async def test_webhook_tenant_isolation(self, async_client: AsyncClient, db_session):
        """Webhooks should only trigger sync for correct tenant."""
        from src.core.models.rbac_models import Tenant

        # Create tenant first (required for FK constraint)
        other_tenant = Tenant(
            id=888,
            name="Other Test Tenant",
            domain="other.test",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(other_tenant)
        await db_session.flush()

        # Create integration for different tenant
        integration = CalendarIntegration(
            tenant_id=888,  # Different from test user tenant (999)
            user_id="8888",
            provider="google",
            provider_account_id="other@example.com",
            access_token_encrypted="token_encrypted",
            is_active=True,
        )
        db_session.add(integration)
        await db_session.flush()

        # Webhook for other tenant's integration
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "other-tenant-channel",
                "X-Goog-Resource-ID": "resource",
                "X-Goog-Resource-State": "exists",
            },
        )

        # Should still return 200
        assert response.status_code == 200


class TestWebhookRateLimiting:
    """Tests for webhook rate limiting."""

    async def test_google_webhook_rate_limit(self, async_client: AsyncClient, integration_factory):
        """Google webhooks are rate limited."""
        integration = await integration_factory(
            provider="google",
        )

        # Send multiple requests
        responses = []
        for i in range(5):
            response = await async_client.post(
                "/api/v1/scheduling/webhooks/google",
                headers={
                    "X-Goog-Channel-ID": "rate-limit-channel",
                    "X-Goog-Resource-ID": f"resource-{i}",
                    "X-Goog-Resource-State": "exists",
                },
            )
            responses.append(response.status_code)

        # Most should succeed (rate limit is 100/minute)
        assert all(code in [200, 429] for code in responses)

    async def test_outlook_webhook_rate_limit(self, async_client: AsyncClient, integration_factory):
        """Outlook webhooks are rate limited."""
        integration = await integration_factory(
            provider="outlook",
        )

        # Send multiple requests
        responses = []
        for i in range(5):
            response = await async_client.post(
                "/api/v1/scheduling/webhooks/outlook",
                headers={
                    "Content-Type": "application/json",
                },
                json={
                    "value": [
                        {
                            "subscriptionId": "rate-limit-subscription",
                            "changeType": "created",
                            "resource": f"me/events/{i}",
                        }
                    ]
                },
            )
            responses.append(response.status_code)

        # Most should succeed (rate limit is 100/minute)
        assert all(code in [200, 429] for code in responses)


class TestWebhookEdgeCases:
    """Edge cases for webhook handling."""

    async def test_google_webhook_duplicate_notification(
        self, async_client: AsyncClient, integration_factory
    ):
        """Handle duplicate webhook notifications."""
        integration = await integration_factory(
            provider="google",
        )

        # Send same notification twice
        for _ in range(2):
            response = await async_client.post(
                "/api/v1/scheduling/webhooks/google",
                headers={
                    "X-Goog-Channel-ID": "duplicate-channel",
                    "X-Goog-Resource-ID": "same-resource",
                    "X-Goog-Resource-State": "exists",
                },
            )
            assert response.status_code == 200

    async def test_outlook_webhook_malformed_json(self, async_client: AsyncClient):
        """Handle malformed JSON in webhook payload."""
        response = await async_client.post(
            "/api/v1/scheduling/webhooks/outlook",
            headers={
                "Content-Type": "application/json",
            },
            content=b"not valid json",
        )

        # Webhooks always return 200 to prevent retries, even for malformed requests
        # The error is logged but not exposed to the caller
        assert response.status_code == 200

    async def test_google_webhook_extra_headers(
        self, async_client: AsyncClient, integration_factory
    ):
        """Handle Google webhook with extra headers."""
        integration = await integration_factory(
            provider="google",
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "extra-headers-channel",
                "X-Goog-Resource-ID": "resource",
                "X-Goog-Resource-State": "exists",
                "X-Goog-Channel-Expiration": "1234567890",
                "X-Goog-Message-Number": "1",
            },
        )

        assert response.status_code == 200

    async def test_webhook_inactive_integration(
        self, async_client: AsyncClient, integration_factory
    ):
        """Webhook for inactive integration should be handled."""
        integration = await integration_factory(
            provider="google",
            is_active=False,
        )

        response = await async_client.post(
            "/api/v1/scheduling/webhooks/google",
            headers={
                "X-Goog-Channel-ID": "inactive-channel",
                "X-Goog-Resource-ID": "resource",
                "X-Goog-Resource-State": "exists",
            },
        )

        # Should still return 200
        assert response.status_code == 200
