"""Unit tests for tools versions router (src/core/api/v1/tools/versions_router.py).

Covers:
- GET /{tool_id}/versions
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.tools.versions_router import (
    get_tool_versions,
    versions_router,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


class DummyToolVersion:
    def __init__(self) -> None:
        self.id = 10
        self.tool_id = 5
        self.version = 1
        self.snapshot = {"name": "calculator"}
        self.created_at = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)


def test_routes_registered() -> None:
    routes = [r for r in versions_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/{tool_id}/versions" in paths


@pytest.mark.asyncio
async def test_get_tool_versions_tool_not_found_raises_404() -> None:
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    user = DummyUser(id=1, tenant_id=42)

    with pytest.raises(HTTPException) as exc_info:
        await get_tool_versions(tool_id=999, db=db, current_user=user)
    assert exc_info.value.status_code == 404
    assert "Tool 999 not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tool_versions_success() -> None:
    db = AsyncMock()
    user = DummyUser(id=1, tenant_id=42)

    mock_owner = MagicMock()
    mock_owner.scalar_one_or_none.return_value = 5

    mock_count = MagicMock()
    mock_count.scalar_one.return_value = 1

    mock_versions = MagicMock()
    mock_versions.scalars.return_value.all.return_value = [DummyToolVersion()]

    db.execute.side_effect = [mock_owner, mock_count, mock_versions]

    res = await get_tool_versions(tool_id=5, skip=0, limit=50, db=db, current_user=user)
    assert res.total == 1
    assert len(res.data) == 1
    assert res.data[0].tool_id == 5
    assert res.data[0].version == 1
    assert res.page == 1
    assert res.per_page == 50
