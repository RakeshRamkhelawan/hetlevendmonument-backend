"""Unit tests for agentic routing router (src/core/api/v1/agentic/agentic_routing_router.py).

Covers:
- POST /route
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.agentic.agentic_routing_router import (
    RouteRequest,
    agentic_routing_router,
    route_query,
)
from src.core.exceptions import AuthError
from src.core.routing.router_orchestrator import RouterResponse


def test_routes_registered() -> None:
    routes = [r for r in agentic_routing_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/route" in paths


@pytest.mark.asyncio
async def test_route_query_success() -> None:
    fake_resp = RouterResponse(
        target_supervisor="supervisor_finance",
        confidence=0.95,
        target_cluster="finance",
        reason="Matched financial keywords",
        layer_used="guna",
    )

    with patch("src.core.api.v1.agentic.agentic_routing_router.require_tenant_id", return_value=42), patch(
        "src.core.api.v1.agentic.agentic_routing_router.GunaRouter.route", new=AsyncMock(return_value=fake_resp)
    ):
        req = RouteRequest(query="Calculate tax returns")
        res = await route_query(request=req, service=None, _current_user=object())
        assert res.supervisor_id == "supervisor_finance"
        assert res.confidence == 0.95
        assert res.routing_path == ["supervisor_finance"]


@pytest.mark.asyncio
async def test_route_query_auth_error_returns_401() -> None:
    with patch("src.core.api.v1.agentic.agentic_routing_router.require_tenant_id", side_effect=AuthError("No tenant")):
        req = RouteRequest(query="test")
        with pytest.raises(HTTPException) as exc_info:
            await route_query(request=req, service=None, _current_user=object())
        assert exc_info.value.status_code == 401
