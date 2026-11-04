import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.core.api.v1.canvas.collaborators_router import (
    collaborators_router,
    add_collaborator,
    remove_collaborator,
)
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import CollaboratorCreate, CollaboratorRole
from src.domains.canvas.service import CanvasService


def test_routes_registered() -> None:
    paths = [r.path for r in collaborators_router.routes]
    assert "/{canvas_id}/collaborators" in paths
    assert "/{canvas_id}/collaborators/{user_id}" in paths


@pytest.mark.asyncio
async def test_add_collaborator_success() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    collaborator_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_obj = {
        "id": collaborator_id,
        "canvas_id": canvas_id,
        "user_id": user_id,
        "role": CollaboratorRole.EDITOR,
        "added_by": uuid4(),
        "added_at": datetime.now(timezone.utc),
        "user_name": "Test User",
        "user_avatar": None,
    }
    mock_service.add_collaborator = AsyncMock(return_value=mock_obj)

    data = CollaboratorCreate(user_id=user_id, role=CollaboratorRole.EDITOR)
    res = await add_collaborator(canvas_id=canvas_id, data=data, service=mock_service)
    assert res.id == collaborator_id
    assert res.canvas_id == canvas_id
    assert res.role == CollaboratorRole.EDITOR


@pytest.mark.asyncio
async def test_add_collaborator_not_found() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.add_collaborator = AsyncMock(side_effect=NotFoundError("Canvas not found"))

    data = CollaboratorCreate(user_id=user_id, role=CollaboratorRole.VIEWER)
    with pytest.raises(HTTPException) as exc_info:
        await add_collaborator(canvas_id=canvas_id, data=data, service=mock_service)
    assert exc_info.value.status_code == 404
    assert "Canvas not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_add_collaborator_forbidden() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.add_collaborator = AsyncMock(side_effect=PermissionDeniedError("write", "canvas", str(user_id)))

    data = CollaboratorCreate(user_id=user_id, role=CollaboratorRole.VIEWER)
    with pytest.raises(HTTPException) as exc_info:
        await add_collaborator(canvas_id=canvas_id, data=data, service=mock_service)
    assert exc_info.value.status_code == 403
    assert "denied" in exc_info.value.detail


@pytest.mark.asyncio
async def test_remove_collaborator_success() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.remove_collaborator = AsyncMock(return_value=None)

    await remove_collaborator(canvas_id=canvas_id, user_id=user_id, service=mock_service)
    assert mock_service.remove_collaborator.called


@pytest.mark.asyncio
async def test_remove_collaborator_not_found() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.remove_collaborator = AsyncMock(side_effect=NotFoundError("Collaborator not found"))

    with pytest.raises(HTTPException) as exc_info:
        await remove_collaborator(canvas_id=canvas_id, user_id=user_id, service=mock_service)
    assert exc_info.value.status_code == 404
    assert "Collaborator not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_remove_collaborator_forbidden() -> None:
    canvas_id = uuid4()
    user_id = uuid4()
    mock_service = MagicMock(spec=CanvasService)
    mock_service.remove_collaborator = AsyncMock(side_effect=PermissionDeniedError("delete", "collaborator", str(user_id)))

    with pytest.raises(HTTPException) as exc_info:
        await remove_collaborator(canvas_id=canvas_id, user_id=user_id, service=mock_service)
    assert exc_info.value.status_code == 403
    assert "denied" in exc_info.value.detail
