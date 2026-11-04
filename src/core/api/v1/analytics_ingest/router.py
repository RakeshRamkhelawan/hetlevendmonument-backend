"""
Composite router for analytics_ingest domain (ADR-033 Laag 1).

Assembles all analytics event ingestion sub-routers under prefix /analytics.
Max 200 lines -- delegates all logic to sub-routers.
"""

from fastapi import APIRouter

from src.core.api.v1.analytics_ingest.dashboard_router import router as dashboard_router
from src.core.api.v1.analytics_ingest.events_router import router as events_router
from src.core.api.v1.analytics_ingest.gdpr_router import router as gdpr_router

router = APIRouter(prefix="/analytics", tags=["analytics-ingest"])

router.include_router(events_router)
router.include_router(gdpr_router)
router.include_router(dashboard_router)
