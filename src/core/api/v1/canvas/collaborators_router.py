# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Canvas collaborator endpoints (ADR-033 Laag 1)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.core.api.v1.canvas.dependencies import get_canvas_service
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import CollaboratorCreate, CollaboratorRead
from src.domains.canvas.service import CanvasService

collaborators_router = APIRouter()


@collaborators_router.post(
    "/{canvas_id}/collaborators",
    response_model=CollaboratorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add collaborator",
)
async def add_collaborator(
    canvas_id: UUID,
    data: CollaboratorCreate,
    service: CanvasService = Depends(get_canvas_service),
) -> CollaboratorRead:
    """Add a collaborator to the canvas."""
    try:
        collaborator = await service.add_collaborator(canvas_id, data)
        return CollaboratorRead.model_validate(collaborator)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@collaborators_router.delete(
    "/{canvas_id}/collaborators/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove collaborator",
    response_class=Response,
)
async def remove_collaborator(
    canvas_id: UUID,
    user_id: UUID,
    service: CanvasService = Depends(get_canvas_service),
) -> None:
    """Remove a collaborator from the canvas."""
    try:
        await service.remove_collaborator(canvas_id, user_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
