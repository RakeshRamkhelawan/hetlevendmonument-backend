"""Synthesis domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as synth_composite_router

domain_router = APIRouter(tags=["Synthesis"])
domain_router.include_router(synth_composite_router)

__all__ = ["domain_router"]
