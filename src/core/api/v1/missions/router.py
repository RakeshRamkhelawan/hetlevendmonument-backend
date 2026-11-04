"""
Missions composite router (ADR-033 Laag 1, max 200r).

Assembles crud_router + lifecycle_router under prefix /missions.
"""

from fastapi import APIRouter

from src.core.api.v1.missions.crud_router import router as crud_router
from src.core.api.v1.missions.lifecycle_router import router as lifecycle_router

router = APIRouter(prefix="/missions", tags=["Missions"])
router.include_router(crud_router)
router.include_router(lifecycle_router)

__all__ = ["router"]
