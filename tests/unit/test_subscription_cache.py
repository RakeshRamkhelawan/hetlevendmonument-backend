# tests/unit/test_subscription_cache.py
import json
import logging
import pytest
from unittest.mock import AsyncMock, patch

from src.core.services.subscription_cache import TenantSubscriptionCache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_get_hit():
    mock_cache = AsyncMock()
    mock_cache.get.return_value = {"tier": "pro", "status": "active"}

    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)
    result = await service.get()

    assert result == {"tier": "pro", "status": "active"}
    mock_cache.get.assert_awaited_once_with("tenant_sub:1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_get_miss():
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None

    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)
    result = await service.get()

    assert result is None
    mock_cache.get.assert_awaited_once_with("tenant_sub:1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_set():
    mock_cache = AsyncMock()
    mock_cache.set.return_value = True

    # Test met standaard TTL (10 min = 600s)
    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)
    result = await service.set(tier="pro", status="active")

    assert result is True
    mock_cache.set.assert_awaited_once_with(
        "tenant_sub:1", {"tier": "pro", "status": "active"}, 600
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_set_custom_config():
    mock_cache = AsyncMock()
    mock_cache.set.return_value = True

    # Test met configureerbare key en TTL
    service = TenantSubscriptionCache(
        tenant_id=2, cache_layer=mock_cache, ttl=300, key_prefix="custom_sub"
    )
    result = await service.set(tier="enterprise", status="trialing")

    assert result is True
    mock_cache.set.assert_awaited_once_with(
        "custom_sub:2", {"tier": "enterprise", "status": "trialing"}, 300
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_delete():
    mock_cache = AsyncMock()
    mock_cache.delete.return_value = True

    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)
    result = await service.delete()

    assert result is True
    mock_cache.delete.assert_awaited_once_with("tenant_sub:1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_error_handling(caplog):
    mock_cache = AsyncMock()
    mock_cache.get.side_effect = Exception("Redis connection failed")

    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)

    # Fout in get() mag niet crashen, moet None retourneren en loggen met exc_info
    with caplog.at_level(logging.ERROR):
        result = await service.get()

    assert result is None
    assert "Error retrieving subscription cache for tenant 1" in caplog.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_cache_set_error_handling(caplog):
    mock_cache = AsyncMock()
    mock_cache.set.side_effect = Exception("Redis write failed")

    service = TenantSubscriptionCache(tenant_id=1, cache_layer=mock_cache)

    with caplog.at_level(logging.ERROR):
        result = await service.set("pro", "active")

    assert result is False
    assert "Error setting subscription cache for tenant 1" in caplog.text
