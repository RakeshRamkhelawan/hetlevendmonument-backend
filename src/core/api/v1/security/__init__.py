"""Security domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as security_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Security"])
domain_router.include_router(security_composite_router)

__all__ = ["domain_router"]
