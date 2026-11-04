"""Feature Flags domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as ff_composite_router

domain_router = APIRouter(prefix="/api", tags=["Feature Flags"])
domain_router.include_router(ff_composite_router)

__all__ = ["domain_router"]
