"""
Feature Flags composite router (ADR-033 Laag 1).

Assembles the three sub-routers without adding its own prefix.
The prefix="/api" is applied at the domain level in __init__.py.
"""

from fastapi import APIRouter

from .admin_router import router as admin_router
from .features_router import router as features_router
from .tenant_router import router as tenant_router

router = APIRouter()
router.include_router(features_router)
router.include_router(tenant_router)
router.include_router(admin_router)
