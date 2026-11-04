"""Admin domain package (ADR-033 Laag 2).

URL prefix: /admin (zonder /api/v1/) -- sub-routers bevatten de volledige prefix.
"""

from fastapi import APIRouter

from .router import router as admin_composite_router

domain_router = APIRouter(tags=["Admin"])
domain_router.include_router(admin_composite_router)

__all__ = ["domain_router"]
