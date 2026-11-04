import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.core.api.v1.activepieces.catalog_router import (
    router,
    get_integration_sources,
    get_piece_details,
)
from src.core.activepieces.schemas import PieceRead
from src.core.activepieces.service import ActivePiecesService
from src.core.auth.api_deps import UserResponse
from tests.helpers.limiet_request import echte_request


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/integrations/source-badges" in paths
    assert "/integrations/pieces/{piece_name}" in paths


@pytest.mark.asyncio
async def test_get_integration_sources_success() -> None:
    service = MagicMock(spec=ActivePiecesService)
    piece = PieceRead(
        name="gmail",
        displayName="Google Gmail",
        version="0.1.0",
        description="Send and receive email",
    )
    service.get_all_pieces = AsyncMock(return_value=[piece])
    user = MagicMock(spec=UserResponse)

    res = await get_integration_sources(request=echte_request(), service=service, _current_user=user)
    assert len(res) == 1
    assert res[0].name == "gmail"
    assert res[0].display_name == "Google Gmail"


@pytest.mark.asyncio
async def test_get_integration_sources_unconfigured() -> None:
    service = MagicMock(spec=ActivePiecesService)
    service.get_all_pieces = AsyncMock(side_effect=ValueError("ActivePieces credentials not configured"))
    user = MagicMock(spec=UserResponse)

    res = await get_integration_sources(request=echte_request(), service=service, _current_user=user)
    assert res == []


@pytest.mark.asyncio
async def test_get_integration_sources_unexpected_error() -> None:
    service = MagicMock(spec=ActivePiecesService)
    service.get_all_pieces = AsyncMock(side_effect=RuntimeError("connection dropped"))
    user = MagicMock(spec=UserResponse)

    with pytest.raises(HTTPException) as exc_info:
        await get_integration_sources(request=echte_request(), service=service, _current_user=user)
    assert exc_info.value.status_code == 500
    assert "unexpected error occurred" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_piece_details_success() -> None:
    service = MagicMock(spec=ActivePiecesService)
    piece = PieceRead(
        name="slack",
        displayName="Slack",
        version="1.0.0",
    )
    service.get_piece_by_name = AsyncMock(return_value=piece)
    user = MagicMock(spec=UserResponse)

    res = await get_piece_details(request=echte_request(), piece_name="slack", service=service, _current_user=user)
    assert res.name == "slack"
    assert res.display_name == "Slack"


@pytest.mark.asyncio
async def test_get_piece_details_not_found() -> None:
    service = MagicMock(spec=ActivePiecesService)
    service.get_piece_by_name = AsyncMock(return_value=None)
    user = MagicMock(spec=UserResponse)

    with pytest.raises(HTTPException) as exc_info:
        await get_piece_details(request=echte_request(), piece_name="unknown_piece", service=service, _current_user=user)
    assert exc_info.value.status_code == 404
    assert "unknown_piece" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_piece_details_error() -> None:
    service = MagicMock(spec=ActivePiecesService)
    service.get_piece_by_name = AsyncMock(side_effect=RuntimeError("db failed"))
    user = MagicMock(spec=UserResponse)

    with pytest.raises(HTTPException) as exc_info:
        await get_piece_details(request=echte_request(), piece_name="slack", service=service, _current_user=user)
    assert exc_info.value.status_code == 500
    assert "unexpected error occurred" in exc_info.value.detail
