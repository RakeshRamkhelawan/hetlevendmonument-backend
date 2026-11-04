"""Unit tests for knowledge admin router (src/core/api/v1/knowledge/admin_router.py).

Covers:
- POST /index/rebuild
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.knowledge.admin_router import (
    rebuild_knowledge_index,
    router,
)
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/index/rebuild" in paths


@pytest.mark.asyncio
async def test_rebuild_knowledge_index_success() -> None:
    user = UserResponse(id="1", email="admin@example.com", tenant_id="42", role="admin")
    distributor = AsyncMock()
    distributor._running = False

    fake_result = MagicMock()
    fake_result.success = True
    fake_result.response_data = {"indexed_count": 150}
    distributor.dispatch_task.return_value = fake_result

    resp = await rebuild_knowledge_index(
        current_user=user,
        _=1,
        task_distributor=distributor,
    )
    distributor.start.assert_awaited_once()
    distributor.dispatch_task.assert_awaited_once()
    assert resp.success is True
    assert resp.agent_response == {"indexed_count": 150}


@pytest.mark.asyncio
async def test_rebuild_knowledge_index_failure_raises_500() -> None:
    user = UserResponse(id="1", email="admin@example.com", tenant_id="42", role="admin")
    distributor = AsyncMock()
    distributor._running = True

    fake_result = MagicMock()
    fake_result.success = False
    fake_result.error_message = "Vector database unreachable"
    distributor.dispatch_task.return_value = fake_result

    with pytest.raises(HTTPException) as exc_info:
        await rebuild_knowledge_index(
            current_user=user,
            _=1,
            task_distributor=distributor,
        )
    assert exc_info.value.status_code == 500
    assert "Vector database unreachable" in exc_info.value.detail
