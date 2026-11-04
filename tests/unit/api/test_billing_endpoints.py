"""Unit tests for billing endpoints (src/core/api/billing_endpoints.py)."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.billing_endpoints import router
from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import Tenant, User

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 123
    user.email = "test@example.com"
    user.tenant_id = 1
    user.stripe_customer_id = "cus_existing123"
    return user


@pytest.fixture
def app(mock_db: AsyncMock, mock_user: MagicMock) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_user] = lambda: mock_user
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_create_checkout_session_success(client: TestClient, mock_db: AsyncMock) -> None:
    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.id = 1
    mock_tenant.stripe_customer_id = "cus_123"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.services.stripe_service.stripe_service.create_checkout_session", return_value="https://stripe.test/checkout"):
        response = client.post("/billing/create-checkout-session?price_id=price_pro_monthly")

    assert response.status_code == 200
    assert response.json() == {"url": "https://stripe.test/checkout"}


def test_create_checkout_session_tenant_not_found_raises_404(client: TestClient, mock_db: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = client.post("/billing/create-checkout-session?price_id=price_pro_monthly")
    assert response.status_code == 404
    assert response.json()["detail"] == "Tenant not found"


def test_create_checkout_session_creates_stripe_customer_if_missing(client: TestClient, mock_db: AsyncMock) -> None:
    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.id = 1
    mock_tenant.stripe_customer_id = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.services.stripe_service.stripe_service.create_customer", return_value="cus_new_123") as mock_create_customer, \
         patch("src.core.services.stripe_service.stripe_service.create_checkout_session", return_value="https://stripe.test/checkout"):
        response = client.post("/billing/create-checkout-session?price_id=price_pro_monthly")

    assert response.status_code == 200
    assert response.json() == {"url": "https://stripe.test/checkout"}
    assert mock_create_customer.called
    assert mock_tenant.stripe_customer_id == "cus_new_123"


def test_get_billing_status_from_cache(client: TestClient) -> None:
    with patch("src.core.api.billing_endpoints.TenantSubscriptionCache") as mock_cache_cls:
        mock_cache = AsyncMock()
        mock_cache.get.return_value = {"tier": "Pro", "status": "Active"}
        mock_cache_cls.return_value = mock_cache

        response = client.get("/billing/status")

    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "pro"
    assert data["status"] == "active"
    assert data["has_stripe_id"] is True


def test_get_billing_status_from_db_on_cache_miss(client: TestClient, mock_db: AsyncMock) -> None:
    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.subscription_tier = "Enterprise"
    mock_tenant.subscription_status = "Active"
    mock_tenant.stripe_customer_id = "cus_ent_123"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.billing_endpoints.TenantSubscriptionCache") as mock_cache_cls:
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None
        mock_cache.set = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        response = client.get("/billing/status")

    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "enterprise"
    assert data["status"] == "active"
    assert data["has_stripe_id"] is True
    assert mock_cache.set.called
