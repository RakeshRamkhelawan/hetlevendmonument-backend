# tests/unit/test_feature_guard_decorator.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.core.security.feature_guard import RequireTier

app = FastAPI()


@app.get("/pro-only")
async def pro_endpoint(_: None = Depends(RequireTier("pro"))):
    return {"status": "ok"}


client = TestClient(app)


@pytest.mark.unit
@patch("src.core.security.feature_guard.get_tenant_id")
@patch("src.core.security.feature_guard.TenantSubscriptionCache")
def test_feature_guard_blocks_insufficient_tiers(mock_cache_class, mock_get_tenant_id):
    mock_get_tenant_id.return_value = 1
    mock_cache = AsyncMock()
    # Return free tier from cache
    mock_cache.get = AsyncMock(return_value={"tier": "free", "status": "active"})
    mock_cache_class.return_value = mock_cache

    response = client.get("/pro-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tier_insufficient"


@pytest.mark.unit
@patch("src.core.security.feature_guard.get_tenant_id")
@patch("src.core.security.feature_guard.TenantSubscriptionCache")
def test_feature_guard_allows_sufficient_tiers(mock_cache_class, mock_get_tenant_id):
    mock_get_tenant_id.return_value = 1
    mock_cache = AsyncMock()
    # Return pro tier from cache
    mock_cache.get = AsyncMock(return_value={"tier": "pro", "status": "active"})
    mock_cache_class.return_value = mock_cache

    response = client.get("/pro-only")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.unit
@patch("src.core.security.feature_guard.get_tenant_id")
@patch("src.core.security.feature_guard.TenantSubscriptionCache")
def test_feature_guard_blocks_canceled_status(mock_cache_class, mock_get_tenant_id):
    """A tenant with tier 'pro' but status 'canceled' must be rejected."""
    mock_get_tenant_id.return_value = 1
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={"tier": "pro", "status": "canceled"})
    mock_cache_class.return_value = mock_cache

    response = client.get("/pro-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "subscription_inactive"


@pytest.mark.unit
@patch("src.core.security.feature_guard.get_tenant_id")
def test_feature_guard_rejects_missing_tenant(mock_get_tenant_id):
    """No tenant context must result in 401."""
    mock_get_tenant_id.return_value = None

    response = client.get("/pro-only")
    assert response.status_code == 401
    assert response.json()["detail"] == "No active tenant context found."
