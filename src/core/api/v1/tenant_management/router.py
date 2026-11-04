# orphan:exempt -- imported via v1/tenant_management/__init__.py -> app_factory.py + main.py (SP-API-004 Dag 4)
"""Tenant management composite router (ADR-033 Laag 1).

Prefix /tenants is applied here; domain_router in __init__.py applies /api/v1.
Max 200 lines.
"""

from fastapi import APIRouter

from src.core.api.v1.tenant_management.crud_router import router as crud_router

router = APIRouter(prefix="/tenants", tags=["tenant-management"])
router.include_router(crud_router)

__all__ = ["router"]
