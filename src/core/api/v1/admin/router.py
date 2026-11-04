"""Admin composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .ap_verbinding_router import router as ap_verbinding_router
from .llm_providers_router import router as llm_providers_router
from .monitoring_router import router as monitoring_router
from .users_router import router as users_router

router = APIRouter()
router.include_router(users_router)
router.include_router(monitoring_router)
router.include_router(llm_providers_router)
router.include_router(ap_verbinding_router)

__all__ = ["router"]
