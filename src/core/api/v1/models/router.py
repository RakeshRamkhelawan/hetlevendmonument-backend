"""Models API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .registry_router import router as registry_router

router = APIRouter()
router.include_router(registry_router)
