"""Production composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .health_router import router as health_router
from .operations_router import router as operations_router
from .reporting_router import router as reporting_router

router = APIRouter(prefix="/v1/production", tags=["Production"])
router.include_router(health_router)
router.include_router(operations_router)
router.include_router(reporting_router)

__all__ = ["router"]
