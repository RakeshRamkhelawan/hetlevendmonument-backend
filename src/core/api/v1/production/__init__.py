"""Production domain package (ADR-033 Laag 2).

Registry analytics.py adds /api prefix at Laag 3.
router.py uses prefix=/v1/production so combined routes land at /api/v1/production/...
"""

from fastapi import APIRouter

from .router import router as prod_composite_router

domain_router = APIRouter(prefix="/api", tags=["Production"])
domain_router.include_router(prod_composite_router)

__all__ = ["domain_router"]
