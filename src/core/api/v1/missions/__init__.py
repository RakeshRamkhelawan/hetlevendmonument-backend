"""Missions domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.missions.router import router as missions_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Missions"])
domain_router.include_router(missions_composite_router)

__all__ = ["domain_router"]
