"""RBAC permissions router: user permissions + permission check endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user_id
from src.core.middleware.tenant_context import require_tenant_id
from src.core.api.v1.rbac.dependencies import Permission, RBACService

router = APIRouter(prefix="/rbac", tags=["RBAC"])


class PermissionCheckRequest(BaseModel):
    """Request to check if user has permission."""

    user_id: int
    permission: str
    resource_id: int | None = None
    resource_type: str | None = None


class UserPermissionsResponse(BaseModel):
    """Response with user's permissions."""

    user_id: int
    tenant_id: int
    permissions: list[str]


class PermissionCheckResponse(BaseModel):
    has_permission: bool


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> UserPermissionsResponse:
    """
    Get all permissions for a user.

    Requires: ADMIN or USER_MANAGE permission
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()

    if current_user_id != user_id:
        has_admin = await rbac.user_has_permission(
            current_user_id, Permission.USER_MANAGE, tenant_id
        )
        if not has_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own permissions",
            )

    permissions = await rbac.get_user_permissions(user_id, tenant_id)
    return UserPermissionsResponse(user_id=user_id, tenant_id=tenant_id, permissions=permissions)


@router.post("/permissions/check", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> JSONResponse:
    """
    Check if a user has a specific permission.

    Useful for frontend UI to show/hide features dynamically.
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()

    if current_user_id != request.user_id:
        has_admin = await rbac.user_has_permission(
            current_user_id, Permission.USER_MANAGE, tenant_id
        )
        if not has_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only check your own permissions",
            )

    has_permission = await rbac.user_has_permission(
        user_id=request.user_id,
        permission=request.permission,
        tenant_id=tenant_id,
        resource_id=request.resource_id,
        resource_type=request.resource_type,
    )

    return JSONResponse(content={"has_permission": bool(has_permission)})
