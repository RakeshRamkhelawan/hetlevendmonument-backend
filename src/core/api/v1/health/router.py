"""Health domain composite router (ADR-033 Laag 1, ADR-012 3-tier health).

Assembles checks_router and llm_router into one composite.
Max 200 lines.
"""

from fastapi import APIRouter

from src.core.api.v1.health.checks_router import router as checks_router
from src.core.api.v1.health.llm_router import router as llm_router

router = APIRouter()
router.include_router(checks_router)
router.include_router(llm_router)

__all__ = ["router"]
