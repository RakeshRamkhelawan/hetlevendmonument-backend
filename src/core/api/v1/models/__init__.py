"""Models Registry domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter
from .router import router as models_composite_router

domain_router = APIRouter(tags=["Model Registry"])
domain_router.include_router(models_composite_router)

__all__ = ["domain_router"]
