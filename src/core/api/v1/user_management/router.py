# orphan:exempt -- composite router; package registered via auth_admin registry
"""User Management composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .crud_router import router as crud_router
from .profile_router import router as profile_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(profile_router)

__all__ = ["router"]
