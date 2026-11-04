# orphan:exempt -- domain package; imported via app_factory.py (deprecated shim) and auth_admin registry
"""User Management domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as user_mgmt_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["User Management"])
domain_router.include_router(user_mgmt_composite_router)

__all__ = ["domain_router"]
