"""Experimentation domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as exp_composite_router

domain_router = APIRouter(tags=["Experimentation"])
domain_router.include_router(exp_composite_router)

__all__ = ["domain_router"]
