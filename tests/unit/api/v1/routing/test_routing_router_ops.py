import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.main import app
from src.core.api.v1.routing.router_ops import (
    router,
    test_routing as endpoint_test_routing,
    report_routing_feedback,
    RouteRequest,
)
from src.core.api.v1.routing.dependencies import Department
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/test" in paths
    assert "/feedback" in paths


@pytest.mark.asyncio
async def test_test_routing_success() -> None:
    user = MagicMock(spec=UserResponse)
    mock_guna = MagicMock()
    mock_result = MagicMock()
    mock_result.department = Department.STRATEGY
    mock_result.guna_used = "sattvic"
    mock_result.confidence = 0.95
    mock_result.prana_cost = 5
    mock_result.reasoning = "High-level goal requires strategic planning"
    mock_result.fallback_used = False
    mock_guna.route = AsyncMock(return_value=mock_result)

    orig = getattr(app.state, "guna_router", None)
    app.state.guna_router = mock_guna
    try:
        req = RouteRequest(task="Define quarterly OKRs")
        res = await endpoint_test_routing(request=req, current_user=user)
        assert res.department == "strategy"
        assert res.guna_used == "sattvic"
        assert res.confidence == 0.95
        assert res.prana_cost == 5
    finally:
        app.state.guna_router = orig


@pytest.mark.asyncio
async def test_test_routing_not_initialized() -> None:
    user = MagicMock(spec=UserResponse)
    orig = getattr(app.state, "guna_router", None)
    app.state.guna_router = None
    try:
        req = RouteRequest(task="Test task")
        with pytest.raises(HTTPException) as exc_info:
            await endpoint_test_routing(request=req, current_user=user)
        assert exc_info.value.status_code == 500
        assert "Internal error" in exc_info.value.detail
    finally:
        app.state.guna_router = orig


@pytest.mark.asyncio
async def test_report_routing_feedback_success() -> None:
    user = MagicMock(spec=UserResponse)
    mock_guna = MagicMock()
    mock_guna.report_outcome = AsyncMock(return_value=None)

    orig = getattr(app.state, "guna_router", None)
    app.state.guna_router = mock_guna
    try:
        res = await report_routing_feedback(
            task="Ship product update",
            predicted_department="operations",
            actual_department="strategy",
            success=True,
            current_user=user,
        )
        assert res == {"message": "Feedback recorded, thank you!"}
        mock_guna.report_outcome.assert_awaited_once()
    finally:
        app.state.guna_router = orig


@pytest.mark.asyncio
async def test_report_routing_feedback_invalid_department() -> None:
    user = MagicMock(spec=UserResponse)
    mock_guna = MagicMock()

    orig = getattr(app.state, "guna_router", None)
    app.state.guna_router = mock_guna
    try:
        with pytest.raises(HTTPException) as exc_info:
            await report_routing_feedback(
                task="Ship product update",
                predicted_department="invalid_dept",
                actual_department="strategy",
                success=True,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "Invalid department" in exc_info.value.detail
    finally:
        app.state.guna_router = orig
