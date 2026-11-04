"""Sentiment Scanner composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .scanner_router import router as scanner_router

router = APIRouter()
router.include_router(scanner_router)

__all__ = ["router"]
