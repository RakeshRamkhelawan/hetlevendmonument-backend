"""
Composite router for monitoring_v1 domain (ADR-033 Laag 1).

Assembles monitoring health, metrics, alerts, and dashboard sub-routers
under prefix /monitoring.
"""

from fastapi import APIRouter

from src.core.api.v1.monitoring_v1.alerts_router import router as alerts_router
from src.core.api.v1.monitoring_v1.dashboard_router import router as dashboard_router
from src.core.api.v1.monitoring_v1.health_router import router as health_router
from src.core.api.v1.monitoring_v1.metrics_router import router as metrics_router

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

router.include_router(health_router)
router.include_router(metrics_router)
router.include_router(alerts_router)
router.include_router(dashboard_router)
