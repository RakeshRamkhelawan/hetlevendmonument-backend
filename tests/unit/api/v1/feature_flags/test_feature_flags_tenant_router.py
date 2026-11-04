"""Unit tests for feature flags tenant router (src/core/api/v1/feature_flags/tenant_router.py).

Covers all 3 endpoints:
- GET /tenant/features
- GET /tenant/tier
- GET /tenant/features/{feature}/check
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.core.api.v1.feature_flags.tenant_router import (
    check_feature,
    get_tenant_features,
    get_tenant_tier,
    router,
)
from src.core.feature_flags import Feature, Tier


class DummyTenant:
    def __init__(self, id: int, plan: str) -> None:
        self.id = id
        self.plan = plan


def _create_mock_request(app_state: dict[str, Any] | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/tenant/features",
        "headers": [],
        "app": MagicMock(),
    }
    state = MagicMock()
    if app_state:
        for k, v in app_state.items():
            setattr(state, k, v)
    else:
        state.ff_manager = None
    scope["app"].state = state
    return Request(scope)


def test_routes_registered() -> None:
    from fastapi.routing import APIRoute

    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/tenant/features" in paths
    assert "/tenant/tier" in paths
    assert "/tenant/features/{feature}/check" in paths


@pytest.mark.asyncio
async def test_get_tenant_features_missing_tenant_context() -> None:
    req = _create_mock_request()
    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_features(request=req, current_user=MagicMock(), db=AsyncMock())
        assert exc_info.value.status_code == 400
        assert "No tenant context available" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tenant_features_not_found() -> None:
    req = _create_mock_request()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value="tenant-99"):
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_features(request=req, current_user=MagicMock(), db=mock_db)
        assert exc_info.value.status_code == 404
        assert "Tenant tenant-99 not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tenant_features_success() -> None:
    req = _create_mock_request()
    mock_db = AsyncMock()
    tenant = DummyTenant(id=1, plan="starter")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=1):
        resp = await get_tenant_features(request=req, current_user=MagicMock(), db=mock_db)
        assert resp.tenant_id == "1"
        assert resp.tier == Tier.STARTER.value
        assert resp.total_features > 0
        assert Feature.CORE_AGENTS.value in resp.enabled_features


@pytest.mark.asyncio
async def test_get_tenant_tier_success() -> None:
    mock_db = AsyncMock()
    tenant = DummyTenant(id=2, plan="starter")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=2):
        resp = await get_tenant_tier(current_user=MagicMock(), db=mock_db)
        assert resp["current_tier"] == Tier.STARTER.value
        assert resp["next_tier"] == Tier.PRO.value
        assert "upgrade_price" in resp
        assert "upgrade_url" in resp


@pytest.mark.asyncio
async def test_get_tenant_tier_not_found() -> None:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=99):
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_tier(current_user=MagicMock(), db=mock_db)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_check_feature_invalid_feature() -> None:
    req = _create_mock_request()
    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=1):
        with pytest.raises(HTTPException) as exc_info:
            await check_feature(
                feature="nonexistent_feature_12345",
                request=req,
                current_user=MagicMock(),
                db=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "Invalid feature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_feature_service_unavailable() -> None:
    req = _create_mock_request(app_state={"ff_manager": None})
    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=1):
        with pytest.raises(HTTPException) as exc_info:
            await check_feature(
                feature=Feature.CORE_AGENTS.value,
                request=req,
                current_user=MagicMock(),
                db=AsyncMock(),
            )
        assert exc_info.value.status_code == 503
        assert "Feature flag service unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_feature_success() -> None:
    mock_ff = AsyncMock()
    mock_ff.is_enabled.return_value = True
    req = _create_mock_request(app_state={"ff_manager": mock_ff})

    mock_db = AsyncMock()
    tenant = DummyTenant(id=1, plan="starter")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tenant
    mock_db.execute.return_value = mock_result

    with patch("src.core.api.v1.feature_flags.tenant_router.get_tenant_id", return_value=1):
        resp = await check_feature(
            feature=Feature.CORE_AGENTS.value,
            request=req,
            current_user=MagicMock(),
            db=mock_db,
        )
        assert resp["feature"] == Feature.CORE_AGENTS.value
        assert resp["enabled"] is True
        assert resp["upgrade_required"] is False
        assert resp["upgrade_url"] is None
