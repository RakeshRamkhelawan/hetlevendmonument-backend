"""RBAC domain router package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as rbac_composite_router

domain_router = APIRouter(prefix="/api", tags=["RBAC"])
domain_router.include_router(rbac_composite_router)

__all__ = ["domain_router"]
