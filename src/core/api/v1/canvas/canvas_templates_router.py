"""Canvas templates sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

from typing import Any

from fastapi import APIRouter, Depends, status

from src.core.api.v1.canvas.dependencies import get_canvas_service
from src.domains.canvas.schemas import CanvasRead
from src.domains.canvas.service import CanvasService

canvas_templates_router = APIRouter()


@canvas_templates_router.get(
    "/templates/list",
    response_model=list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    summary="List templates",
)
async def list_templates() -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Get available canvas templates."""
    return [
        {
            "id": "blank",
            "name": "Blank Canvas",
            "description": "Start with an empty canvas",
            "icon": "square",
        },
        {
            "id": "strategy",
            "name": "Strategy Map",
            "description": "Goals, initiatives, and KPIs",
            "icon": "target",
        },
        {
            "id": "workflow",
            "name": "Workflow",
            "description": "Process flow with agents",
            "icon": "git-branch",
        },
        {
            "id": "dashboard",
            "name": "Dashboard",
            "description": "Metrics and charts",
            "icon": "bar-chart",
        },
    ]


@canvas_templates_router.post(
    "/from-template/{template_id}",
    response_model=CanvasRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create from template",
)
async def create_from_template(
    template_id: str,
    name: str,
    service: CanvasService = Depends(get_canvas_service),
) -> CanvasRead:
    """Create a new canvas from a template."""
    from src.domains.canvas.schemas import CanvasCreate

    data = CanvasCreate(name=name, template=template_id)
    canvas = await service.create_canvas(data)
    return CanvasRead.model_validate(canvas)
