"""
Analytics ingest domain -- event collection, metrics, GDPR, dashboard.

Migrated from src/core/api/analytics_endpoints.py (SP-API-003 Dag 4).
"""

from fastapi import APIRouter

from src.core.api.v1.analytics_ingest.router import router as analytics_ingest_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Analytics"])
domain_router.include_router(analytics_ingest_composite_router)

__all__ = ["domain_router"]
