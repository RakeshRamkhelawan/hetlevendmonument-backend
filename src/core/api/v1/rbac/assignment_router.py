"""RBAC assignment router: assign/revoke roles, bulk operations."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user_id
from src.core.middleware.tenant_context import require_tenant_id
from src.core.api.v1.rbac.dependencies import RBACService, require_user_manage

# De rolcontrole staat op de router: elke route hieronder vraagt dezelfde permissie, en als
# dependency komt de 403 voor de validatie van de body (plan nazorg, punt d).
router = APIRouter(prefix="/rbac", tags=["RBAC"], dependencies=[Depends(require_user_manage)])


class RoleAssignmentRequest(BaseModel):
    """Request to assign/revoke a role."""

    user_id: int
    role_name: str


class BulkRoleAssignmentRequest(BaseModel):
    """Bulk role assignment/revocation request."""

    user_ids: list[int]
    role_name: str


def _eis_dat_de_rol_uitgedeeld_mag_worden(toegestaan: bool) -> None:
    """403 voor een platformrol die de aanvrager zelf niet heeft (zie `RBACService.mag_rol_uitdelen`)."""
    if not toegestaan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deze rol kan alleen door een platformbeheerder worden toegekend.",
        )


@router.post("/users/assign-role")
async def assign_role_to_user(
    request: RoleAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Assign a role to a user.

    Requires: ADMIN or USER_MANAGE permission
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    _eis_dat_de_rol_uitgedeeld_mag_worden(
        await rbac.mag_rol_uitdelen(current_user_id, request.role_name, tenant_id)
    )

    success = await rbac.assign_role(
        request.user_id, request.role_name, tenant_id, assigned_by=current_user_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to assign role '%s'" % request.role_name,
        )

    return {
        "success": True,
        "message": "Role '%s' assigned to user %s" % (request.role_name, request.user_id),
    }


@router.post("/users/revoke-role")
async def revoke_role_from_user(
    request: RoleAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Revoke a role from a user.

    Requires: ADMIN or USER_MANAGE permission
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()


    # Een rol die de gebruiker niet heeft intrekken is geen succes en geen auditregel: 404.
    if not await rbac.user_has_role(request.user_id, request.role_name, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User %s does not have role '%s'" % (request.user_id, request.role_name),
        )
    try:
        success = await rbac.revoke_role(
            request.user_id, request.role_name, tenant_id, revoked_by=current_user_id
        )
    except PermissionError as exc:
        # De regel zit in de dienst (RBACService.mag_rol_uitdelen): een platformrol ontneemt alleen wie hem zelf heeft.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geen toegang.") from exc

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to revoke role '%s'" % request.role_name,
        )

    return {
        "success": True,
        "message": "Role '%s' revoked from user %s" % (request.role_name, request.user_id),
    }


@router.post("/users/assign-role/bulk")
async def bulk_assign_role(
    request: BulkRoleAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Assign a role to multiple users (USER_MANAGE required)."""
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    _eis_dat_de_rol_uitgedeeld_mag_worden(
        await rbac.mag_rol_uitdelen(current_user_id, request.role_name, tenant_id)
    )
    results = await rbac.bulk_assign_roles(
        request.user_ids, request.role_name, tenant_id, assigned_by=current_user_id
    )
    return {"success": True, "results": results}


@router.post("/users/revoke-role/bulk")
async def bulk_revoke_role(
    request: BulkRoleAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Revoke a role from multiple users (USER_MANAGE required)."""
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    try:
        results = await rbac.bulk_revoke_roles(
            request.user_ids, request.role_name, tenant_id, revoked_by=current_user_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geen toegang.") from exc
    return {"success": True, "results": results}
