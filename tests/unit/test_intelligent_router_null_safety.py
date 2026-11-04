"""
Null-safety test for IntelligentRouter.route() -> Optional[RoutingDecision].

Pre-existing bug found during SP-TYPE-01 dag 6: route_request endpoint
accessed decision.selected_route etc. without checking for None first.
IntelligentRouter.route() returns None when no routes are available OR
when the routing strategy fails to select a route.

Fix: if decision is None: raise HTTPException(503, "Router returned no decision")
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_request_raises_503_when_router_returns_none() -> None:
    """route_request must return HTTP 503 when IntelligentRouter.route() returns None."""
    from src.core.api.v1.ai_features.routing_router import RoutingRequest, route_request
    from src.core.auth.auth_service import UserResponse

    mock_router = AsyncMock()
    mock_router.route.return_value = None  # simulates no available routes

    mock_user = MagicMock(spec=UserResponse)
    mock_user.id = 42
    mock_user.tenant_id = 1

    request = RoutingRequest(
        request_id="test-req-001",
        request_type="inference",
        priority="normal",
    )

    with pytest.raises(HTTPException) as exc_info:
        await route_request(
            request=request,
            current_user=mock_user,
            _=1,
            router_instance=mock_router,
        )

    assert exc_info.value.status_code == 503
    assert "no decision" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_request_succeeds_when_router_returns_decision() -> None:
    """route_request must succeed and return RoutingDecisionResponse when router returns a decision."""
    from src.core.api.v1.ai_features.routing_router import RoutingRequest, route_request
    from src.core.auth.auth_service import UserResponse

    mock_route = MagicMock()
    mock_route.to_dict.return_value = {"id": "route-1", "name": "primary"}

    mock_decision = MagicMock()
    mock_decision.selected_route = mock_route
    mock_decision.confidence = 0.92
    mock_decision.reasoning = "High-confidence match"
    mock_decision.alternative_routes = []
    mock_decision.decision_time = 0.003

    mock_router = AsyncMock()
    mock_router.route.return_value = mock_decision

    mock_user = MagicMock(spec=UserResponse)
    mock_user.id = 42
    mock_user.tenant_id = 1

    request = RoutingRequest(
        request_id="test-req-002",
        request_type="inference",
        priority="high",
    )

    result = await route_request(
        request=request,
        current_user=mock_user,
        _=1,
        router_instance=mock_router,
    )

    assert result.request_id == "test-req-002"
    assert result.confidence == 0.92
    assert result.selected_route == {"id": "route-1", "name": "primary"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_intelligent_router_route_returns_none_when_no_routes() -> None:
    """IntelligentRouter.route_request returns None when no routes registered."""
    from src.core.ai.intelligent_routing import IntelligentRouter, RequestContext

    router = IntelligentRouter()
    await router.initialize()
    # No routes registered -> route_request returns None
    from src.core.ai.intelligent_routing import RequestPriority

    ctx = RequestContext(
        request_id="ctx-001",
        user_id="user-1",
        session_id=None,
        request_type="inference",
        priority=RequestPriority.NORMAL,
        payload_size=0,
        expected_complexity="medium",
    )
    result = await router.route_request(ctx)
    assert result is None, "Expected None when no routes are available"
    await router.cleanup()
