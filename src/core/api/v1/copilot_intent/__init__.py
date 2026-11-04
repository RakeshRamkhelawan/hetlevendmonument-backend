"""Copilot Intent Parser domain package (ADR-033 Laag 2).

Migrated from src/core/api/copilot_endpoints.py (SP-API-006 Dag 1).
"""

from fastapi import APIRouter

from .router import router as ci_composite_router

domain_router = APIRouter(tags=["Copilot - Intent Parser"])
domain_router.include_router(ci_composite_router)

__all__ = ["domain_router"]
