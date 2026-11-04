"""Management domain router package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as management_composite_router

# NOTE: management_endpoints.py uses prefix="/api/v1" internally on each sub-router,
# so domain_router has NO additional prefix to avoid double-prefix.
domain_router = APIRouter(tags=["management"])
domain_router.include_router(management_composite_router)

__all__ = ["domain_router"]
