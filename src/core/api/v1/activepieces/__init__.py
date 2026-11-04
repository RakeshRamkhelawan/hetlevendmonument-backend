"""ActivePieces Integration domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as ap_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Integrations"])
domain_router.include_router(ap_composite_router)

__all__ = ["domain_router"]
