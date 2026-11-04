"""Governance Admin domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.governance_admin.router import router as gov_admin_router

domain_router = APIRouter(tags=["governance"])
domain_router.include_router(gov_admin_router)

__all__ = ["domain_router"]
