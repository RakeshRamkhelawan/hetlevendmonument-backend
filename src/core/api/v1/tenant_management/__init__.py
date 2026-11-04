# orphan:exempt -- legacy domain package; registration removed from app_factory (AUDIT-DB-01).
"""Legacy tenant management domain package (DEPRECATED).

domain_router prefix: /api/v1 (router.py adds /tenants).
This router is no longer registered by the canonical app factory in src.main;
it is kept only for backward compatibility with direct imports.
"""

from fastapi import APIRouter

from src.core.api.v1.tenant_management.router import router as tenant_management_router

domain_router = APIRouter(prefix="/api/v1", tags=["tenant-management"])
domain_router.include_router(tenant_management_router)

__all__ = ["domain_router"]
