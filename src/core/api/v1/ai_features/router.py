# orphan:exempt reason: Laag 1 composite router, registered transitively via __init__.py (ADR-033)
"""AI Features composite router (ADR-033 Laag 1) -- assembles sub-routers."""

from fastapi import APIRouter

from src.core.api.v1.ai_features.analytics_router import router as analytics_sub_router
from src.core.api.v1.ai_features.learning_router import router as learning_sub_router
from src.core.api.v1.ai_features.routing_router import router as routing_sub_router
from src.core.api.v1.ai_features.system_router import router as system_sub_router

router = APIRouter()
router.include_router(learning_sub_router)
router.include_router(routing_sub_router)
router.include_router(analytics_sub_router)
router.include_router(system_sub_router)
