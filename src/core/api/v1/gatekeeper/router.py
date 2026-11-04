"""Gatekeeper API router (composite).

Re-exports decisions + HITL sub-routers.
Original 360-line router split into two <=200-line modules per ADR-033.
"""

from fastapi import APIRouter

from .gatekeeper_decisions_router import router as decisions_router
from .gatekeeper_hitl_router import router as hitl_router

from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

router = APIRouter()
router.include_router(decisions_router)
router.include_router(hitl_router)
