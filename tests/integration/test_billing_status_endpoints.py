# tests/integration/test_billing_status_endpoints.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.core.auth.dependencies import get_current_user
from src.core.models.rbac_models import Tenant, User
from src.main import create_test_app


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 123
    user.tenant_id = 456
    user.email = "test-status@example.com"
    user.stripe_customer_id = "cus_mock_status"
    user.subscription_tier = "Pro"
    user.subscription_status = "Active"
    user.full_name = "Test Status User"
    return user


@pytest.fixture
def auth_headers():
    from src.core.auth.jwt_handler import jwt_handler

    token = jwt_handler.create_access_token(
        data={"sub": "test-status@example.com", "tenant_id": 456, "roles": ["user"]}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_client(mock_user, account_actief_zonder_database):
    """De tokens horen bij verzonnen gebruikers: de accountcontrole van de middleware (3fa4f2d2) staat uit."""
    import os

    with patch.dict(os.environ, {"ENABLE_SECURITY_MIDDLEWARE": "false"}):
        test_app = create_test_app()
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(test_app, raise_server_exceptions=False)
    yield client
    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("src.core.api.billing_endpoints.TenantSubscriptionCache")
async def test_console_billing_status_returns_lowercase_keys(
    mock_cache_class, test_client, mock_user, auth_headers
):
    """
    Test that calling /api/v1/billing/status returns lowercased keys for tier and status.
    It should attempt to retrieve from the cache first.
    """
    # Setup mock cache to return mixed-case subscription
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={"tier": "PRO", "status": "ACTIVE"})
    mock_cache_class.return_value = mock_cache

    # We need to mock get_tenant_id to return our tenant_id
    with patch("src.core.api.billing_endpoints.get_tenant_id", return_value=456):
        response = test_client.get("/api/v1/billing/status", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify keys exist and are lowercased
        assert "tier" in data
        assert "status" in data
        assert "has_stripe_id" in data

        assert data["tier"] == "pro"
        assert data["status"] == "active"
        assert data["has_stripe_id"] is True

        mock_cache.get.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.core.api.billing_endpoints.TenantSubscriptionCache")
async def test_console_billing_status_cache_miss_db_fallback(
    mock_cache_class, test_client, mock_user, auth_headers
):
    """
    Test that on cache miss, the endpoint falls back to the database to fetch subscription.
    """
    # Setup mock cache to miss (return None)
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=True)
    mock_cache_class.return_value = mock_cache

    # Create a mock database session
    mock_db = AsyncMock()
    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.subscription_tier = "Starter"
    mock_tenant.subscription_status = "Trialing"

    # Setup database query result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_tenant
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Override get_db dependency to return our mock database session
    from src.core.database.database import get_db

    test_client.app.dependency_overrides[get_db] = lambda: mock_db

    with patch("src.core.api.billing_endpoints.get_tenant_id", return_value=456):
        response = test_client.get("/api/v1/billing/status", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["tier"] == "starter"
        assert data["status"] == "trialing"

        mock_cache.get.assert_awaited_once()
        mock_cache.set.assert_awaited_once_with(tier="starter", status="trialing")
