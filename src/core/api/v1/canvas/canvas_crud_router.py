# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Canvas CRUD endpoints (ADR-033 Laag 1)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.core.api.v1.canvas.dependencies import get_canvas_service
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import (
    CanvasCreate,
    CanvasListRead,
    CanvasRead,
    CanvasUpdate,
)
from src.domains.canvas.service import CanvasService

canvas_crud_router = APIRouter()


@canvas_crud_router.post(
    "/",
    response_model=CanvasRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new canvas",
)
async def create_canvas(
    data: CanvasCreate,
    service: CanvasService = Depends(get_canvas_service),
) -> CanvasRead:
    """Create a new collaborative canvas."""
    canvas = await service.create_canvas(data)
    return CanvasRead.model_validate(canvas)


@canvas_crud_router.get(
    "/",
    response_model=list[CanvasListRead],
    summary="List canvases",
)
async def list_canvases(
    search: str | None = Query(None, description="Search by name"),
    template: str | None = Query(None, description="Filter by template"),
    owner_only: bool = Query(False, description="Only show owned canvases"),
    shared_only: bool = Query(False, description="Only show shared canvases"),
    service: CanvasService = Depends(get_canvas_service),
) -> list[CanvasListRead]:
    """List all accessible canvases with optional filters."""
    canvases = await service.list_canvases(
        search=search,
        template=template,
        owner_only=owner_only,
        shared_only=shared_only,
    )
    return [CanvasListRead.model_validate(c) for c in canvases]


@canvas_crud_router.get(
    "/{canvas_id}",
    response_model=CanvasRead,
    summary="Get canvas by ID",
)
async def get_canvas(
    canvas_id: UUID,
    service: CanvasService = Depends(get_canvas_service),
) -> CanvasRead:
    """Get a specific canvas with all blocks and connections."""
    try:
        canvas = await service.get_canvas(canvas_id)
        return CanvasRead.model_validate(canvas)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@canvas_crud_router.patch(
    "/{canvas_id}",
    response_model=CanvasRead,
    summary="Update canvas",
)
async def update_canvas(
    canvas_id: UUID,
    data: CanvasUpdate,
    service: CanvasService = Depends(get_canvas_service),
) -> CanvasRead:
    """Update canvas metadata (name, visibility)."""
    try:
        canvas = await service.update_canvas(canvas_id, data)
        return CanvasRead.model_validate(canvas)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@canvas_crud_router.delete(
    "/{canvas_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete canvas",
    response_class=Response,
)
async def delete_canvas(
    canvas_id: UUID,
    service: CanvasService = Depends(get_canvas_service),
) -> None:
    """Delete a canvas and all its data."""
    try:
        await service.delete_canvas(canvas_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
