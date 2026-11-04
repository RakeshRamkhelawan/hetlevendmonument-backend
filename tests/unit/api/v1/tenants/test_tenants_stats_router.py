"""Unit tests for tenants stats router (src.core.api.v1.tenants.tenants_stats_router).

Follows Pattern A from API-LAAG-MASTERPROMPT.md: calling endpoint handlers directly
with mocked dependencies for strict tenant isolation and authorization verification.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.tenants.dependencies import TenantService
from src.core.api.v1.tenants.schemas import TenantStats
from src.core.api.v1.tenants.tenants_stats_router import get_tenant_stats, tenants_stats_router


@pytest.fixture
def mock_service() -> AsyncMock:
    svc = AsyncMock(spec=TenantService)
    return svc


@pytest.fixture
def mock_superuser() -> MagicMock:
    user = MagicMock()
    user.is_superuser = True
    user.tenant_id = 1
    user.id = 101
    return user


@pytest.fixture
def mock_regular_user() -> MagicMock:
    user = MagicMock()
    user.is_superuser = False
    user.tenant_id = 1
    user.id = 102
    return user


def test_tenants_stats_router_route_registration() -> None:
    """Verify route path and method in tenants_stats_router."""
    from fastapi.routing import APIRoute

    api_routes = [r for r in tenants_stats_router.routes if isinstance(r, APIRoute)]
    route_paths = [r.path for r in api_routes]
    assert "/{tenant_id}/stats" in route_paths
    route = next(r for r in api_routes if r.path == "/{tenant_id}/stats")
    assert "GET" in route.methods



@pytest.mark.unit
async def test_get_tenant_stats_cross_tenant_isolation_blocked(
    mock_service: AsyncMock, mock_regular_user: MagicMock
) -> None:
    """Verify tenant isolation: regular user cannot access stats of another tenant."""
    # User belongs to tenant 1, requests stats for tenant 2
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_stats(
            tenant_id=2, service=mock_service, current_user=mock_regular_user
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You can only access your own tenant statistics"
    mock_service.get_tenant_stats.assert_not_awaited()


@pytest.mark.unit
async def test_get_tenant_stats_superuser_can_access_any_tenant(
    mock_service: AsyncMock, mock_superuser: MagicMock
) -> None:
    """Verify platform superuser can access stats across tenants."""
    mock_stats = MagicMock(spec=TenantStats)
    mock_service.get_tenant_stats.return_value = mock_stats

    # Superuser (tenant 1) requests stats for tenant 2
    result = await get_tenant_stats(
        tenant_id=2, service=mock_service, current_user=mock_superuser
    )

    assert result is mock_stats
    mock_service.get_tenant_stats.assert_awaited_once_with(2)


@pytest.mark.unit
async def test_get_tenant_stats_own_tenant_success(
    mock_service: AsyncMock, mock_regular_user: MagicMock
) -> None:
    """Verify regular user can access their own tenant statistics."""
    mock_stats = MagicMock(spec=TenantStats)
    mock_service.get_tenant_stats.return_value = mock_stats

    # Regular user (tenant 1) requests stats for tenant 1
    result = await get_tenant_stats(
        tenant_id=1, service=mock_service, current_user=mock_regular_user
    )

    assert result is mock_stats
    mock_service.get_tenant_stats.assert_awaited_once_with(1)


@pytest.mark.unit
async def test_get_tenant_stats_not_found_returns_404(
    mock_service: AsyncMock, mock_regular_user: MagicMock
) -> None:
    """Verify 404 is returned when tenant stats do not exist."""
    mock_service.get_tenant_stats.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_stats(
            tenant_id=1, service=mock_service, current_user=mock_regular_user
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail
