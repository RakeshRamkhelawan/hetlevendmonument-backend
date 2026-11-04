"""Composite router for Experimentation domain (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .experiments_router import router as experiments_router

router = APIRouter(prefix="/api/v1/experiments")
router.include_router(experiments_router)

__all__ = ["router"]
