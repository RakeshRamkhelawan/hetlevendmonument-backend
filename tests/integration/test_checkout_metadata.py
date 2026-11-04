# tests/integration/test_checkout_metadata.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import status
from fastapi.testclient import TestClient

from src.main import create_test_app
from src.core.auth.dependencies import get_current_user
from src.core.models.rbac_models import User


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 123
    user.tenant_id = 1  # seeded tenant in integration DB
    user.email = "test-metadata@example.com"
    user.stripe_customer_id = "cus_mock_123456"
    user.subscription_tier = None
    user.subscription_status = None
    user.full_name = "Test Metadata User"
    return user


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
async def test_checkout_session_metadata_passing(test_client, mock_user):
    """
    Test that calling /api/v1/billing/create-checkout-session passes
    the tenant_id and subscription_tier in metadata to Stripe.
    """
    from src.core.services.stripe_service import stripe_service

    mock_create = AsyncMock(return_value="https://checkout.stripe.com/mock/session/cs_123")
    # Tenant 1 has no stripe_customer_id in the seeded DB, so create_customer
    # is called before create_checkout_session. Mock it to avoid real Stripe calls.
    mock_customer = AsyncMock(return_value="cus_mock_for_test")

    with (
        patch.object(stripe_service, "create_checkout_session", mock_create),
        patch.object(stripe_service, "create_customer", mock_customer),
    ):
        from src.core.auth.jwt_handler import jwt_handler

        token = jwt_handler.create_access_token(
            {"sub": "test-metadata@example.com", "tenant_id": 1}
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = test_client.post(
            "/api/v1/billing/create-checkout-session?price_id=price_pro_monthly", headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["url"] == "https://checkout.stripe.com/mock/session/cs_123"

        mock_create.assert_called_once()
        kwargs = mock_create.call_args[1]

        assert "metadata" in kwargs
        assert kwargs["metadata"] == {
            "tenant_id": "1",
            "subscription_tier": "pro",
        }
