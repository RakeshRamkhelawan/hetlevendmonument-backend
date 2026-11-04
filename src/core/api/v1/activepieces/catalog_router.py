"""ActivePieces catalog sub-router: source badges and piece details."""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.core.exceptions.exceptions import SanskritiError
from src.core.activepieces.schemas import PieceRead
from src.core.activepieces.service import ActivePiecesService, get_activepieces_service
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.api.v1.activepieces.dependencies import integration_read_limit
from loguru import logger

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get(
    "/source-badges",
    response_model=list[PieceRead],
    summary="Get all available integration sources",
    description="Fetches available ActivePieces integrations (pieces) for displaying source badges.",
)
@integration_read_limit
async def get_integration_sources(
    request: Request,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[PieceRead]:
    """Get list of available integrations."""
    try:
        return await service.get_all_pieces()
    except ValueError as e:
        if "credentials not configured" in str(e):
            logger.warning("ActivePieces not configured, returning empty source badges")
            return []
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/pieces/{piece_name}",
    response_model=PieceRead,
    summary="Get piece details",
    description="Get detailed information about a specific piece/integration.",
)
@integration_read_limit
async def get_piece_details(
    request: Request,
    piece_name: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> PieceRead:
    """Get detailed information about a specific piece."""
    try:
        piece = await service.get_piece_by_name(piece_name)
        if not piece:
            raise HTTPException(status_code=404, detail=f"Piece '{piece_name}' not found")
        return piece
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
