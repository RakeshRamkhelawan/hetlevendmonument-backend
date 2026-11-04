import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.v1.rbac.permissions_router import (
    router,
    get_user_permissions,
    check_permission,
    PermissionCheckRequest,
)


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/rbac/users/{user_id}/permissions" in paths
    assert "/rbac/permissions/check" in paths


@pytest.mark.asyncio
async def test_get_user_permissions_own_success() -> None:
    db = MagicMock()
    with patch("src.core.api.v1.rbac.permissions_router.require_tenant_id", return_value=1), \
         patch("src.core.api.v1.rbac.permissions_router.RBACService") as mock_rbac_cls:
        rbac = MagicMock()
        rbac.get_user_permissions = AsyncMock(return_value=["READ", "WRITE"])
        mock_rbac_cls.return_value = rbac

        res = await get_user_permissions(user_id=10, db=db, current_user_id=10)
        assert res.user_id == 10
        assert res.tenant_id == 1
        assert res.permissions == ["READ", "WRITE"]


@pytest.mark.asyncio
async def test_get_user_permissions_other_forbidden() -> None:
    db = MagicMock()
    with patch("src.core.api.v1.rbac.permissions_router.require_tenant_id", return_value=1), \
         patch("src.core.api.v1.rbac.permissions_router.RBACService") as mock_rbac_cls:
        rbac = MagicMock()
        rbac.user_has_permission = AsyncMock(return_value=False)
        mock_rbac_cls.return_value = rbac

        with pytest.raises(HTTPException) as exc_info:
            await get_user_permissions(user_id=20, db=db, current_user_id=10)
        assert exc_info.value.status_code == 403
        assert "only view your own" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_permission_own_success() -> None:
    db = MagicMock()
    with patch("src.core.api.v1.rbac.permissions_router.require_tenant_id", return_value=1), \
         patch("src.core.api.v1.rbac.permissions_router.RBACService") as mock_rbac_cls:
        rbac = MagicMock()
        rbac.user_has_permission = AsyncMock(return_value=True)
        mock_rbac_cls.return_value = rbac

        req = PermissionCheckRequest(user_id=10, permission="EXECUTE")
        res = await check_permission(request=req, db=db, current_user_id=10)
        import json
        data = json.loads(res.body.decode())
        assert data["has_permission"] is True


@pytest.mark.asyncio
async def test_check_permission_other_forbidden() -> None:
    db = MagicMock()
    with patch("src.core.api.v1.rbac.permissions_router.require_tenant_id", return_value=1), \
         patch("src.core.api.v1.rbac.permissions_router.RBACService") as mock_rbac_cls:
        rbac = MagicMock()
        rbac.user_has_permission = AsyncMock(return_value=False)
        mock_rbac_cls.return_value = rbac

        req = PermissionCheckRequest(user_id=20, permission="EXECUTE")
        with pytest.raises(HTTPException) as exc_info:
            await check_permission(request=req, db=db, current_user_id=10)
        assert exc_info.value.status_code == 403
        assert "only check your own" in exc_info.value.detail
