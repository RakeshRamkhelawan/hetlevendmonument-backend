"""Agents domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.agents.router import router as agents_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Agents"])
domain_router.include_router(agents_composite_router)

__all__ = ["domain_router"]
