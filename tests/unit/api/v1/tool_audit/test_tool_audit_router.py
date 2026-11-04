"""Unit tests for tool audit router (src/core/api/v1/tool_audit/router.py).

Covers:
- GET /tool-audit-logs
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.tool_audit.router import list_tool_audit_logs, router
from src.core.auth.runtime_deps import UserResponse
from tests.helpers.limiet_request import echte_request


class DummyLog:
    def __init__(self) -> None:
        self.id = "log-1"
        self.agent_id = "agent-x"
        self.tool_name = "weather_tool"
        self.risk_level = "low"
        self.status = "success"
        self.task_id = "task-1"
        self.duration_seconds = 0.42
        self.timestamp = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
        self.audit_hash = "abc123hash"


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/tool-audit-logs" in paths


@pytest.mark.asyncio
async def test_list_tool_audit_logs_forbidden_for_non_admin() -> None:
    user = UserResponse(id="2", email="user@example.com", tenant_id="42", role="user")
    repo = AsyncMock()

    with patch("src.core.api.v1.tool_audit.router._is_tenant_admin", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await list_tool_audit_logs(request=echte_request(), current_user=user, repo=repo)
        assert exc_info.value.status_code == 403
        assert "Admin role required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_tool_audit_logs_success_for_admin() -> None:
    admin_user = UserResponse(id="1", email="admin@example.com", tenant_id="42", role="admin")
    repo = AsyncMock()
    repo.count_logs.return_value = 1
    repo.get_logs.return_value = [DummyLog()]

    with patch("src.core.api.v1.tool_audit.router._is_tenant_admin", return_value=True):
        res = await list_tool_audit_logs(request=echte_request(), current_user=admin_user, repo=repo, limit=10, offset=0)
        assert res["success"] is True
        assert res["total"] == 1
        assert len(res["data"]) == 1
        assert res["data"][0]["tool_name"] == "weather_tool"
        assert res["data"][0]["audit_hash"] == "abc123hash"
