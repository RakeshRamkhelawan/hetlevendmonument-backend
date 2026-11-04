# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Canvas block CRUD endpoints (ADR-033 Laag 1)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.core.api.v1.canvas.dependencies import get_canvas_service
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import BlockCreate, BlockRead, BlockUpdate
from src.domains.canvas.service import CanvasService

blocks_router = APIRouter()


@blocks_router.post(
    "/{canvas_id}/blocks",
    response_model=BlockRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create block",
)
async def create_block(
    canvas_id: UUID,
    data: BlockCreate,
    service: CanvasService = Depends(get_canvas_service),
) -> BlockRead:
    """Add a new block to the canvas."""
    try:
        block = await service.create_block(canvas_id, data)
        return BlockRead.model_validate(block)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@blocks_router.patch(
    "/{canvas_id}/blocks/{block_id}",
    response_model=BlockRead,
    summary="Update block",
)
async def update_block(
    canvas_id: UUID,
    block_id: UUID,
    data: BlockUpdate,
    service: CanvasService = Depends(get_canvas_service),
) -> BlockRead:
    """Update a block's position, size, or content."""
    try:
        block = await service.update_block(canvas_id, block_id, data)
        return BlockRead.model_validate(block)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@blocks_router.delete(
    "/{canvas_id}/blocks/{block_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete block",
    response_class=Response,
)
async def delete_block(
    canvas_id: UUID,
    block_id: UUID,
    service: CanvasService = Depends(get_canvas_service),
) -> None:
    """Remove a block from the canvas."""
    try:
        await service.delete_block(canvas_id, block_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
