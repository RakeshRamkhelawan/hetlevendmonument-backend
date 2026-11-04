"""
Memory composite router -- assembles config and index sub-routers.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter

from .config_router import router as config_router
from .index_router import router as index_router

router = APIRouter(prefix="/memory", tags=["Memory"])
router.include_router(config_router)
router.include_router(index_router)
