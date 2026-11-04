"""Security API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .alerts_router import alerts_router
from .auth_router import auth_router
from .management_router import management_router
from .monitoring_router import monitoring_router
from .report_router import report_router

router = APIRouter(prefix="/security")
router.include_router(auth_router)
router.include_router(report_router)
router.include_router(management_router)
router.include_router(monitoring_router)
router.include_router(alerts_router)
