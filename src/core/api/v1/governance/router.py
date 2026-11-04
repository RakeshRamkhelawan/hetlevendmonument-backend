"""Governance REST API router (composite).

Re-exports monitoring + quality sub-routers.
Original 238-line router split into two <=200-line modules per ADR-033.

Dependency re-exports allow tests to override them via
`app.dependency_overrides[get_current_user] = ...` without importing deep sub-modules.
"""

from fastapi import APIRouter

from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

from .governance_monitoring_router import _require_governance_read  # noqa: F401 -- re-export for test overrides
from .governance_monitoring_router import router as monitoring_router
from .governance_quality_router import router as quality_router

router = APIRouter()
router.include_router(monitoring_router)
router.include_router(quality_router)

__all__ = [
    "router",
    "get_current_user",
    "get_current_tenant_id",
    "_require_governance_read",
]
