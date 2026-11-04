"""Canvas API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.canvas.canvas_crud_router import canvas_crud_router
from src.core.api.v1.canvas.blocks_router import blocks_router
from src.core.api.v1.canvas.connections_router import connections_router
from src.core.api.v1.canvas.collaborators_router import collaborators_router
from src.core.api.v1.canvas.canvas_templates_router import canvas_templates_router
from src.core.api.v1.canvas.canvas_ws_router import canvas_ws_router

router = APIRouter(prefix="/canvas", tags=["Canvas"])
router.include_router(canvas_crud_router)
router.include_router(blocks_router)
router.include_router(connections_router)
router.include_router(collaborators_router)
router.include_router(canvas_templates_router)
router.include_router(canvas_ws_router)
