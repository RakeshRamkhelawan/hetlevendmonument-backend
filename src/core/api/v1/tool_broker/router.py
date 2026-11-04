"""Tool Broker composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from src.core.api.v1.tool_broker.crud_router import router as crud_router
from src.core.api.v1.tool_broker.execution_router import router as execution_router
from src.core.api.v1.tool_broker.management_router import router as management_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(execution_router)
router.include_router(management_router)

__all__ = ["router"]
