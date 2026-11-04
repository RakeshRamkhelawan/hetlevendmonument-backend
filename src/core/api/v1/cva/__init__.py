"""CVA domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.cva.router import router as cva_composite_router

# GEEN prefix -- sub-routers hebben al /api/v1/cva of /cva als prefix
domain_router = APIRouter(tags=["CVA"])
domain_router.include_router(cva_composite_router)

__all__ = ["domain_router"]
