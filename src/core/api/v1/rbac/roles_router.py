"""RBAC roles router: create, list, and manage role permissions + users."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user_id
from src.core.middleware.tenant_context import require_tenant_id
from src.core.api.v1.rbac.dependencies import RBACService, ReservedRoleNameError, require_tenant_admin
import logging
logger = logging.getLogger(__name__)

# De rolcontrole staat op de router: elke route hieronder vraagt dezelfde permissie, en als
# dependency komt de 403 voor de validatie van de body (plan nazorg, punt d).
router = APIRouter(prefix="/rbac", tags=["RBAC"], dependencies=[Depends(require_tenant_admin)])


class CreateRoleRequest(BaseModel):
    """Request to create a new role."""

    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., max_length=200)
    permissions: list[dict[str, str]] = Field(
        ...,
        description="List of permissions: [{'resource': 'agent', 'action': 'read'}, ...]",
    )


class RoleResponse(BaseModel):
    """Role information response."""

    id: int
    name: str
    description: str | None
    tenant_id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PermissionEntry(BaseModel):
    resource: str
    action: str
    conditions: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    model_config = ConfigDict(from_attributes=True)


class UserSummaryResponse(BaseModel):
    """Minimal user info for listing by role."""

    id: int
    email: str
    tenant_id: int

    model_config = ConfigDict(from_attributes=True)


@router.post("/roles/create", response_model=RoleResponse)
async def create_role(
    request: CreateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> RoleResponse:
    """
    Create a new custom role with permissions.

    Requires: ADMIN or TENANT_ADMIN permission
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()


    try:
        role = await rbac.create_role(
            name=request.name,
            description=request.description,
            permissions=request.permissions,
            tenant_id=tenant_id,
        )
    except ReservedRoleNameError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    except ValueError as e:
        logger.error("create_role mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.")

    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create role '%s'" % request.name,
        )

    return RoleResponse.model_validate(role)


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> list[RoleResponse]:
    """List all roles for current tenant (TENANT_ADMIN required).

    # TODO(SP-VOLGENDE): voeg limit/offset toe (overgenomen van rbac_endpoints.py zonder paginering)
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    # Een platformrol staat alleen in de lijst voor wie hem zelf heeft: de lijst voedt de rolkeuze in
    # het scherm, en een keuze die de server toch weigert is een val.
    roles = await rbac.list_roles_voor(current_user_id, tenant_id)
    return [RoleResponse.model_validate(r) for r in roles]


@router.get("/roles/{role_id}/permissions", response_model=list[PermissionEntry])
async def list_role_permissions(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> list[PermissionEntry]:
    """List all permissions attached to a role (TENANT_ADMIN required)."""
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    perms = await rbac.list_role_permissions(role_id)
    return [PermissionEntry.model_validate(p) for p in perms]


@router.post("/roles/{role_id}/permissions")
async def add_role_permission(
    role_id: int,
    entry: PermissionEntry,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Add a permission to a role (TENANT_ADMIN required)."""
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    # `tenant_id` gaat EXPLICIET mee: de dienst controleert daarmee dat `role_id` -- dat
    # rechtstreeks uit het URL-pad komt -- bij DEZE klant hoort, en werpt anders een 404
    # (ADR-036 OP-256). Zonder die parameter zou de dienst hem uit de context halen; dat
    # werkt hier ook, maar expliciet doorgeven maakt op de aanroepplek zichtbaar dat de
    # klant van de AANVRAGER leidend is en niet die van de opgegeven rol.
    ok = await rbac.add_permission_to_role(
        role_id, entry.resource, entry.action, entry.conditions, tenant_id=tenant_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add permission"
        )
    return {"success": True}


@router.delete("/roles/{role_id}/permissions")
async def remove_role_permission(
    role_id: int,
    entry: PermissionEntry,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Remove a permission from a role (TENANT_ADMIN required)."""
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    # Zelfde klantcontrole als hierboven (ADR-036 OP-256); deze kant was WEL bereikbaar.
    ok = await rbac.remove_permission_from_role(
        role_id, entry.resource, entry.action, tenant_id=tenant_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to remove permission",
        )
    return {"success": True}


@router.get("/roles/{role_id}/users", response_model=list[UserSummaryResponse])
async def list_users_for_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> list[UserSummaryResponse]:
    """List users assigned to a role (TENANT_ADMIN required).

    # TODO(SP-VOLGENDE): voeg limit/offset toe (overgenomen van rbac_endpoints.py zonder paginering)
    """
    rbac = RBACService(db)
    tenant_id = require_tenant_id()
    users = await rbac.list_users_by_role(role_id, tenant_id)
    return [UserSummaryResponse.model_validate(u) for u in users]
