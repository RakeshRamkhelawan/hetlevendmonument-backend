"""
Audit composite router -- assembles all audit sub-routers.

Migrated from src/core/api/audit_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter

from .missions_router import router as missions_router

router = APIRouter(prefix="/audit", tags=["Audit"])
router.include_router(missions_router)
