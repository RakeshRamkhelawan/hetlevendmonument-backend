"""Synthesis composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .synthesis_router import router as synthesis_sub_router

router = APIRouter()
router.include_router(synthesis_sub_router)

__all__ = ["router"]
