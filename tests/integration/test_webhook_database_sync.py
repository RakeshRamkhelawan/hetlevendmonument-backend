# tests/integration/test_webhook_database_sync.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.models.rbac_models import Tenant
from src.core.services.subscription_cache import TenantSubscriptionCache
from src.main import create_test_app


class MockCacheLayer:
    def __init__(self):
        self.store = {}
        self.connected = True

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)
        return True


@pytest.mark.asyncio
async def test_webhook_checkout_completed_sync(integration_client, postgres_session):
    """
    Test that a checkout.session.completed Stripe webhook event correctly
    updates the tenant subscription status, subscription_tier, stripe_customer_id,
    and invalidates/sets the TenantSubscriptionCache, using TenantFilterBypass.
    """
    # 1. Create a tenant in the database
    # In SanskritiSetu, tenants are required to have is_active, etc.
    tenant = Tenant(
        name="Webhook Sync Test Tenant",
        slug="webhook-sync-test",
        domain="sync.test.local",
        is_active=True,
        max_users=10,
        max_agents=5,
        max_storage_gb=50.0,
        subscription_tier="free",
        subscription_status="active",
        stripe_customer_id="cus_sync_test_999",  # Seed customer ID
        data_residency="global",
    )
    postgres_session.add(tenant)
    await postgres_session.commit()
    await postgres_session.refresh(tenant)

    tenant_id = tenant.id

    # 2. Prepare mock Stripe event
    mock_event = {
        "id": "evt_checkout_completed_999",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_sync_test_999",
                "payment_status": "paid",
                "metadata": {"tenant_id": str(tenant_id), "subscription_tier": "pro"},
            }
        },
    }

    # 3. Setup mock cache layer
    mock_cache = MockCacheLayer()

    # 4. Patch stripe event verification and cache layer
    # We bypass signature verification and intercept get_cache to use our MockCacheLayer
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", return_value=mock_event),
        patch("src.core.caching.cache_layer.get_cache", return_value=mock_cache),
        patch("src.core.services.subscription_cache.get_cache", return_value=mock_cache),
        patch("src.core.api.webhooks.stripe_handler.get_redis", AsyncMock()) as mock_redis,
    ):

        # Configure mock redis for two-phase lock
        mock_redis.set.return_value = True

        # Warm up the cache with initial "free" state
        sub_cache = TenantSubscriptionCache(tenant_id=tenant_id, cache_layer=mock_cache)
        await sub_cache.set(tier="free", status="active")

        # Verify initial cache is set
        cached_info = await sub_cache.get()
        assert cached_info == {"tier": "free", "status": "active"}

        # 5. Call the Stripe webhook endpoint
        response = await integration_client.post(
            "/api/v1/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=mock_sig"},
            json={"dummy": "data"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "success"}

        # 6. Verify database changes
        # Use database session to fetch the tenant without tenant RLS filter constraints in tests
        # conftest.py does not enforce RLS on test sessions unless configured, but we bypass to be safe
        from src.core.database.tenant_query_filter import TenantFilterBypass

        with TenantFilterBypass():
            await postgres_session.refresh(tenant)
            assert tenant.subscription_status == "active"
            assert tenant.subscription_tier == "pro"

        # 7. Verify cache is updated/invalidated
        updated_cached_info = await sub_cache.get()
        assert updated_cached_info == {"tier": "pro", "status": "active"}


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_sync(integration_client, postgres_session):
    """
    Test that customer.subscription.deleted Stripe webhook event correctly
    cancels the tenant subscription, sets tier to free, and invalidates/updates the cache.
    """
    # 1. Create a tenant in the database
    tenant = Tenant(
        name="Webhook Delete Test Tenant",
        slug="webhook-delete-test",
        domain="delete.test.local",
        is_active=True,
        max_users=10,
        max_agents=5,
        max_storage_gb=50.0,
        subscription_tier="pro",
        subscription_status="active",
        stripe_customer_id="cus_delete_test_999",
        data_residency="global",
    )
    postgres_session.add(tenant)
    await postgres_session.commit()
    await postgres_session.refresh(tenant)

    tenant_id = tenant.id

    # 2. Prepare mock Stripe event
    mock_event = {
        "id": "evt_subscription_deleted_999",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_delete_test_999",
            }
        },
    }

    # 3. Setup mock cache layer
    mock_cache = MockCacheLayer()

    # 4. Patch stripe event verification and cache layer
    from src.core.config.unified_config import config as unified_config

    with (
        patch.object(unified_config, "stripe_webhook_secret", "whsec_test_secret"),
        patch("stripe.Webhook.construct_event", return_value=mock_event),
        patch("src.core.caching.cache_layer.get_cache", return_value=mock_cache),
        patch("src.core.services.subscription_cache.get_cache", return_value=mock_cache),
        patch("src.core.api.webhooks.stripe_handler.get_redis", AsyncMock()) as mock_redis,
    ):

        # Configure mock redis for two-phase lock
        mock_redis.set.return_value = True

        # Warm up the cache with initial "pro" state
        sub_cache = TenantSubscriptionCache(tenant_id=tenant_id, cache_layer=mock_cache)
        await sub_cache.set(tier="pro", status="active")

        # 5. Call the Stripe webhook endpoint
        response = await integration_client.post(
            "/api/v1/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=mock_sig"},
            json={"dummy": "data"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "success"}

        # 6. Verify database changes
        from src.core.database.tenant_query_filter import TenantFilterBypass

        with TenantFilterBypass():
            await postgres_session.refresh(tenant)
            assert tenant.subscription_status == "canceled"
            assert tenant.subscription_tier == "free"

        # 7. Verify cache is updated/invalidated
        updated_cached_info = await sub_cache.get()
        assert updated_cached_info == {"tier": "free", "status": "canceled"}
