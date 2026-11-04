"""
Knowledge composite router -- assembles CRUD, search, and admin sub-routers.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter

from .admin_router import router as admin_router
from .crud_router import router as crud_router
from .search_router import router as search_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(search_router)
router.include_router(admin_router)
