import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from fastapi import HTTPException, Request

from src.core.api.v1.snapshot_endpoints import router, store_snapshot, get_snapshot
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/snapshots/{workflow_id}" in paths


@pytest.mark.asyncio
async def test_store_snapshot_workflow_not_found() -> None:
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    user = MagicMock(spec=UserResponse)
    user.tenant_id = 1
    user.id = 5

    req = MagicMock(spec=Request)

    with pytest.raises(HTTPException) as exc_info:
        await store_snapshot(workflow_id="wf-1", request=req, db=db, user=user)
    assert exc_info.value.status_code == 404
    assert "Workflow not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_store_snapshot_empty_content() -> None:
    db = MagicMock()
    mock_workflow = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_workflow
    db.execute = AsyncMock(return_value=mock_result)

    user = MagicMock(spec=UserResponse)
    user.tenant_id = 1
    user.id = 5

    req = MagicMock(spec=Request)
    req.body = AsyncMock(return_value=b"")

    with pytest.raises(HTTPException) as exc_info:
        await store_snapshot(workflow_id="wf-1", request=req, db=db, user=user)
    assert exc_info.value.status_code == 400
    assert "Empty snapshot content" in exc_info.value.detail


@pytest.mark.asyncio
async def test_store_snapshot_success() -> None:
    db = MagicMock()
    mock_workflow = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_workflow
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    user = MagicMock(spec=UserResponse)
    user.tenant_id = 1
    user.id = 5

    req = MagicMock(spec=Request)
    req.body = AsyncMock(return_value=b"\x01\x02\x03\x04")

    res = await store_snapshot(workflow_id="wf-1", request=req, db=db, user=user)
    assert res["workflow_id"] == "wf-1"
    assert res["size_bytes"] == 4
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_get_snapshot_success() -> None:
    db = MagicMock()
    mock_workflow = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.content = b"\x01\x02\x03\x04\x05"

    mock_res_wf = MagicMock()
    mock_res_wf.scalars().first.return_value = mock_workflow

    mock_res_snap = MagicMock()
    mock_res_snap.scalars().first.return_value = mock_snapshot

    db.execute = AsyncMock(side_effect=[mock_res_wf, mock_res_snap])

    user = MagicMock(spec=UserResponse)
    user.tenant_id = 1

    res = await get_snapshot(workflow_id="wf-1", db=db, user=user)
    assert res.body == b"\x01\x02\x03\x04\x05"
    assert res.media_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_get_snapshot_not_found() -> None:
    db = MagicMock()
    mock_workflow = MagicMock()
    mock_res_wf = MagicMock()
    mock_res_wf.scalars().first.return_value = mock_workflow

    mock_res_snap = MagicMock()
    mock_res_snap.scalars().first.return_value = None

    db.execute = AsyncMock(side_effect=[mock_res_wf, mock_res_snap])

    user = MagicMock(spec=UserResponse)
    user.tenant_id = 1

    with pytest.raises(HTTPException) as exc_info:
        await get_snapshot(workflow_id="wf-1", db=db, user=user)
    assert exc_info.value.status_code == 404
    assert "No snapshot found" in exc_info.value.detail
