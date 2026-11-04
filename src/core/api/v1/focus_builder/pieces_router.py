"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
FocusBuilder Pieces Catalog sub-router (ADR-033 Laag 1).

Routes:
- GET /pieces
- GET /pieces/{piece_name}/schema
- POST /pieces/sync
"""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

if TYPE_CHECKING:
    from src.domains.flows.service import FocusBuilderService
from loguru import logger

from src.core.api.v1.focus_builder.shared import (
    create_error_response,
    enrich_span,
    get_focus_builder_service,
    limiter,
)
from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_permission, Permission

pieces_router = APIRouter()


@pieces_router.get("/pieces")
@limiter.limit("20/minute")
async def list_pieces(
    request: Request,
    response: Response,
    search: str | None = None,
    category: str | None = None,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    List available integration pieces.
    Rate limit: 20 requests per minute.
    """
    enrich_span(request, current_user.id, operation="list_pieces")
    logger.debug("list_pieces_request", user_id=current_user.id, search=search, category=category)
    pieces = await service.get_pieces_catalog(search, category)
    logger.debug("list_pieces_completed", user_id=current_user.id, count=len(pieces))
    return {"pieces": pieces, "total": len(pieces)}


@pieces_router.get("/pieces/{piece_name}/schema")
@limiter.limit("20/minute")
async def get_piece_schema(
    request: Request,
    response: Response,
    piece_name: str,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get JSON schema for piece configuration.
    Rate limit: 20 requests per minute.
    """
    enrich_span(request, current_user.id, operation="get_piece_schema", piece_name=piece_name)
    logger.debug("get_piece_schema_request", user_id=current_user.id, piece_name=piece_name)
    schema = await service.get_piece_schema(piece_name)
    if not schema:
        logger.warning("get_piece_schema_not_found", user_id=current_user.id, piece_name=piece_name)
        raise HTTPException(
            status_code=404,
            detail=create_error_response("PIECE_NOT_FOUND", f"Piece '{piece_name}' not found"),
        )
    return schema


@pieces_router.post("/pieces/sync", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/minute")
async def sync_pieces(
    request: Request,
    response: Response,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_permission(Permission.ADMIN)),
) -> dict[str, str]:
    """
    Sync pieces catalog from ActivePieces.
    Admin only. Rate limit: 2 requests per minute (heavy operation).
    """
    enrich_span(request, current_user.id, operation="sync_pieces")
    logger.info("sync_pieces_request", user_id=current_user.id)
    try:
        await service.sync_pieces_catalog()
        logger.info("sync_pieces_completed", user_id=current_user.id)
        return {"status": "sync_started", "message": "Pieces catalog sync initiated"}
    except Exception as e:
        logger.error("sync_pieces_error", user_id=current_user.id, error=str(e))
        raise HTTPException(status_code=500, detail=create_error_response("SYNC_FAILED", "Er is een interne fout opgetreden."))
