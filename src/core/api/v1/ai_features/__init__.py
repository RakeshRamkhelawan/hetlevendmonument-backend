# orphan:exempt reason: Laag 2 domain package, registered via registries/analytics.py importlib (ADR-033)
"""AI Features domain package (ADR-033 Laag 2).

Migrated from src/core/api/ai_features_endpoints.py (SP-API-007 Dag 2).
Routes: POST /learning/event, GET /learning/insights, POST /routing/route,
        POST /analytics/predict, GET /system/status, GET /capabilities.
"""

from fastapi import APIRouter

from src.core.api.v1.ai_features.router import router as ai_composite_router

domain_router = APIRouter(prefix="/api/v1/ai", tags=["AI Features"])
domain_router.include_router(ai_composite_router)

__all__ = ["domain_router"]
