import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.v1.feature_flags.admin_router import router, toggle_feature, ToggleFeatureRequest


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/admin/features/{feature}/toggle" in paths


@pytest.mark.asyncio
async def test_toggle_feature_invalid_feature_raises_400() -> None:
    req_body = ToggleFeatureRequest(enabled=True)
    req = MagicMock()
    admin_user = {"user_id": 1, "role": "admin", "tenant_id": 42}

    with patch("src.core.api.v1.feature_flags.admin_router.require_admin", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await toggle_feature(
                feature="non_existent_feature_xyz",
                request_body=req_body,
                request=req,
                target_tenant_id=42,
                admin_user=admin_user,
                db=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "Invalid feature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_toggle_feature_missing_ff_manager_raises_503() -> None:
    req_body = ToggleFeatureRequest(enabled=True)
    req = MagicMock()
    req.app.state.ff_manager = None
    admin_user = {"user_id": 1, "role": "admin", "tenant_id": 42}

    with patch("src.core.api.v1.feature_flags.admin_router.require_admin", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await toggle_feature(
                feature="core_agents",
                request_body=req_body,
                request=req,
                target_tenant_id=42,
                admin_user=admin_user,
                db=AsyncMock(),
            )
        assert exc_info.value.status_code == 503
        assert "Feature flag service unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_toggle_feature_success() -> None:
    req_body = ToggleFeatureRequest(enabled=True)
    req = MagicMock()
    ff_manager = MagicMock()
    ff_manager.redis = AsyncMock()
    ff_manager.CACHE_KEY_PREFIX = "ff:"
    req.app.state.ff_manager = ff_manager

    admin_user = {"user_id": 1, "role": "admin", "tenant_id": 42}
    session = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = None  # creates new flag
    session.execute.return_value = scalar_mock

    with patch("src.core.api.v1.feature_flags.admin_router.require_admin", new_callable=AsyncMock):
        resp = await toggle_feature(
            feature="core_agents",
            request_body=req_body,
            request=req,
            target_tenant_id=42,
            admin_user=admin_user,
            db=session,
        )
        assert resp["success"] is True
        assert resp["feature"] == "core_agents"
        assert resp["tenant_id"] == "42"
        assert resp["enabled"] is True
