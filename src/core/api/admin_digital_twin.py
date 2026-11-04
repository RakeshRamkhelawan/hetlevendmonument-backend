"""
Admin Digital Twin endpoints -- tenant-scoped stats dashboard (ADR-025/026).

Endpoints:
    GET /api/v1/admin/digital-twin/stats
        Returns aggregated twin stats for the caller's JWT tenant.
        system_admin users may supply override_tenant_id to query another tenant.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import consent_read_limit, get_db, get_twin_stats, require_admin_role
from src.core.auth import UserResponse

router = APIRouter(prefix="/admin/digital-twin", tags=["admin-digital-twin"])


def _is_system_admin(user: UserResponse) -> bool:
    roles = getattr(user, "roles", []) or []
    return "system_admin" in roles


def _user_tenant(user: UserResponse) -> int:
    tid = getattr(user, "tenant_id", None)
    if tid is None:
        raise ValueError("User has no tenant_id")
    return int(tid)


@router.get("/stats")
@consent_read_limit
async def get_digital_twin_stats(
    request: Request,
    override_tenant_id: int | None = Query(
        None, description="system_admin only: query a specific tenant"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin_role),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Return aggregated Digital Twin stats for a tenant.

    Tenant is always read from the JWT claim.  Regular admins always see their
    own tenant; system_admin users may supply override_tenant_id.
    """
    tenant_id = _user_tenant(current_user)
    if _is_system_admin(current_user) and override_tenant_id is not None:
        tenant_id = override_tenant_id

    # RLS: scope the session to the queried tenant before any SELECT.
    # `set_config(..., true)` en niet `SET LOCAL ... = :tid`: PostgreSQL accepteert geen
    # bindparameter in een utility-statement. Gemeten 2026-08-16 op het echte pad
    # (SQLAlchemy + asyncpg): de SET LOCAL-vorm gaf `PostgresSyntaxError`, dus dit endpoint
    # kon nooit slagen. Het derde argument `true` maakt het transactie-lokaal, net als
    # SET LOCAL. Dezelfde vorm staat in feature_flags/admin_router.py en
    # copilot/api/audit_endpoints.py.
    await db.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(int(tenant_id))},
    )

    stats = await get_twin_stats(db=db, tenant_id=tenant_id)
    return {"success": True, "data": stats}
