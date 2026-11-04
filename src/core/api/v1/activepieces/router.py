"""ActivePieces composite router (ADR-033 Laag 2 -- transitief via __init__.py)."""

from fastapi import APIRouter

from .catalog_router import router as catalog_router
from .connections_router import router as connections_router
from .execution_router import router as execution_router
from .flows_router import router as flows_router
from .health_router import router as health_router

# NOTE: prefix=/integrations is set on each sub-router; this composite has no own prefix.
router = APIRouter(tags=["Integrations"])

router.include_router(catalog_router)
router.include_router(flows_router)
router.include_router(execution_router)
router.include_router(connections_router)
router.include_router(health_router)

__all__ = ["router"]
