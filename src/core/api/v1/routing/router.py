# orphan:exempt reason: geladen via importlib in registries/agentic.py (dynamisch)
"""Routing API (ADR-033 Laag 1 composiet)."""

from fastapi import APIRouter

from .router_monitor import router as monitor_router
from .router_monitor import routing_health  # noqa: F401 (re-export for tests/shims)
from .router_ops import router as ops_router
from .dependencies import Department  # noqa: F401 (re-export for facade compliance -- ADR-033)

router = APIRouter(prefix="/routing", tags=["routing"])
router.include_router(ops_router)
router.include_router(monitor_router)
