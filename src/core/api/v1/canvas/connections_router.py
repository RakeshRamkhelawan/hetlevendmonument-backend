# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Canvas connection CRUD endpoints (ADR-033 Laag 1)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.core.api.v1.canvas.dependencies import get_canvas_service
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import ConnectionCreate, ConnectionRead
from src.domains.canvas.service import CanvasService

connections_router = APIRouter()


@connections_router.post(
    "/{canvas_id}/connections",
    response_model=ConnectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create connection",
)
async def create_connection(
    canvas_id: UUID,
    data: ConnectionCreate,
    service: CanvasService = Depends(get_canvas_service),
) -> ConnectionRead:
    """Create a connection between two blocks."""
    try:
        connection = await service.create_connection(canvas_id, data)
        return ConnectionRead.model_validate(connection)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@connections_router.delete(
    "/{canvas_id}/connections/{connection_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete connection",
    response_class=Response,
)
async def delete_connection(
    canvas_id: UUID,
    connection_id: UUID,
    service: CanvasService = Depends(get_canvas_service),
) -> None:
    """Remove a connection."""
    try:
        await service.delete_connection(canvas_id, connection_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
