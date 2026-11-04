"""Unit tests for orchestration stats router (src/core/api/v1/orchestration/stats_router.py).

Covers:
- GET /stats
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from src.core.api.v1.orchestration.stats_router import (
    _get_tenant_id,
    get_stats,
    stats_router,
)


def _create_mock_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/stats",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_routes_registered() -> None:
    routes = [r for r in stats_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/stats" in paths


def test_get_tenant_id_missing_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _get_tenant_id(tenant_id=None)
    assert exc_info.value.status_code == 401
    assert "Tenant context required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_stats_success() -> None:
    req = _create_mock_request()
    res = Response()

    orchestrator = MagicMock()
    orchestrator.agent_id = "master-orch-1"
    orchestrator.get_active_workflow_count.return_value = 3

    agent_router = MagicMock()
    agent_router.agent_id = "router-agent-1"
    agent_router.get_cache_stats.return_value = {"hit_rate": 0.85}
    agent_router.get_registered_agent_count.return_value = 10

    health_monitor = MagicMock()
    health_monitor.agent_id = "health-mon-1"

    data = await get_stats(
        request=req,
        response=res,
        orchestrator=orchestrator,
        agent_router=agent_router,
        health_monitor=health_monitor,
        tenant_id=77,
    )
    assert data.tenant_id == 77
    assert data.master_orchestrator_id == "master-orch-1"
    assert data.registered_agents == 10
    assert data.active_workflows == 3
    assert data.cache_stats == {"hit_rate": 0.85}
