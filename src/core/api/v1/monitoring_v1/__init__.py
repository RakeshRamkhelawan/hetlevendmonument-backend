"""
Monitoring domain -- health probes, metrics, alerts, dashboard, WebSocket.

Migrated from monitoring_endpoints.py + monitoring_dashboard_endpoints.py
(SP-API-003 Dag 4).
"""

from fastapi import APIRouter

from src.core.api.v1.monitoring_v1.router import router as monitoring_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Monitoring"])
domain_router.include_router(monitoring_composite_router)

__all__ = ["domain_router"]
