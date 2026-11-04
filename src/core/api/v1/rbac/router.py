"""RBAC composite router -- assembles all sub-routers."""

from fastapi import APIRouter

from .assignment_router import router as assignment_router
from .permissions_router import router as permissions_router
from .roles_router import router as roles_router

router = APIRouter()
router.include_router(permissions_router)
router.include_router(roles_router)
router.include_router(assignment_router)
