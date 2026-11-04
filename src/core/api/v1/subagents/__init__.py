"""Subagents domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as subagents_composite_router

domain_router = APIRouter(tags=["Subagents"])
domain_router.include_router(subagents_composite_router)

__all__ = ["domain_router"]
