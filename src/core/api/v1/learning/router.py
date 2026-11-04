"""Learning domain API router (ADR-033 Laag 1, max 200 regels).

Aggregates:
- rules_router: feedback submission + rules CRUD
- analytics_router: insights, metrics, ROI, reports, ML, regional context
"""

from fastapi import APIRouter

from src.core.api.v1.learning.analytics_router import router as analytics_router
from src.core.api.v1.learning.rules_router import router as rules_router

router = APIRouter(prefix="/learning", tags=["Learning"])
router.include_router(rules_router)
router.include_router(analytics_router)
