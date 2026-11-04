import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.core.api.v1.canvas.connections_router import (
    connections_router,
    create_connection,
    delete_connection,
)
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import ConnectionCreate
from src.domains.canvas.service import CanvasService


def test_routes_registered() -> None:
    paths = [r.path for r in connections_router.routes]
    assert "/{canvas_id}/connections" in paths
    assert "/{canvas_id}/connections/{connection_id}" in paths


@pytest.mark.asyncio
async def test_create_connection_success() -> None:
    canvas_id = uuid4()
    from_block = uuid4()
    to_block = uuid4()
    conn_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_obj = {
        "id": conn_id,
        "canvas_id": canvas_id,
        "from_block_id": from_block,
        "to_block_id": to_block,
        "connection_type": "straight",
        "color": "#000000",
        "label": "Test Link",
        "is_bidirectional": False,
        "trigger": None,
    }
    mock_service.create_connection = AsyncMock(return_value=mock_obj)

    data = ConnectionCreate(from_block_id=from_block, to_block_id=to_block)
    res = await create_connection(canvas_id=canvas_id, data=data, service=mock_service)
    assert res.id == conn_id
    assert res.canvas_id == canvas_id
    assert res.from_block_id == from_block
    assert res.to_block_id == to_block


@pytest.mark.asyncio
async def test_create_connection_not_found() -> None:
    canvas_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.create_connection = AsyncMock(side_effect=NotFoundError("Block not found"))

    data = ConnectionCreate(from_block_id=uuid4(), to_block_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await create_connection(canvas_id=canvas_id, data=data, service=mock_service)
    assert exc_info.value.status_code == 404
    assert "Block not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_connection_forbidden() -> None:
    canvas_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.create_connection = AsyncMock(side_effect=PermissionDeniedError("write", "canvas", "user-1"))

    data = ConnectionCreate(from_block_id=uuid4(), to_block_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await create_connection(canvas_id=canvas_id, data=data, service=mock_service)
    assert exc_info.value.status_code == 403
    assert "denied" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_connection_success() -> None:
    canvas_id = uuid4()
    conn_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.delete_connection = AsyncMock(return_value=None)

    await delete_connection(canvas_id=canvas_id, connection_id=conn_id, service=mock_service)
    assert mock_service.delete_connection.called


@pytest.mark.asyncio
async def test_delete_connection_not_found() -> None:
    canvas_id = uuid4()
    conn_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.delete_connection = AsyncMock(side_effect=NotFoundError("Connection not found"))

    with pytest.raises(HTTPException) as exc_info:
        await delete_connection(canvas_id=canvas_id, connection_id=conn_id, service=mock_service)
    assert exc_info.value.status_code == 404
    assert "Connection not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_connection_forbidden() -> None:
    canvas_id = uuid4()
    conn_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.delete_connection = AsyncMock(side_effect=PermissionDeniedError("write", "canvas", "user-1"))

    with pytest.raises(HTTPException) as exc_info:
        await delete_connection(canvas_id=canvas_id, connection_id=conn_id, service=mock_service)
    assert exc_info.value.status_code == 403
    assert "denied" in exc_info.value.detail
