import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.v1.routing.router_monitor import (
    router,
    get_routing_stats,
    routing_health,
)
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/stats" in paths
    assert "/health" in paths


@pytest.mark.asyncio
async def test_get_routing_stats_success() -> None:
    user = MagicMock(spec=UserResponse)
    mock_guna = MagicMock()
    mock_guna.get_stats.return_value = {
        "total_requests": 100,
        "tamasic_percentage": 50.0,
        "rajasic_percentage": 30.0,
        "sattvic_percentage": 15.0,
        "fallback_percentage": 5.0,
    }
    mock_guna.PRANA_COSTS = {"tamasic": 1, "rajasic": 2, "sattvic": 5}

    with patch("src.main.app.state.guna_router", mock_guna, create=True):
        res = await get_routing_stats(current_user=user)
        assert res["statistics"]["total_requests"] == 100
        assert res["guna_distribution"]["tamasic"] == "50.0%"
        assert res["prana_costs"]["tamasic"] == 1


@pytest.mark.asyncio
async def test_get_routing_stats_not_initialized() -> None:
    user = MagicMock(spec=UserResponse)

    with patch("src.main.app.state.guna_router", None, create=True):
        with pytest.raises(HTTPException) as exc_info:
            await get_routing_stats(current_user=user)
        assert exc_info.value.status_code == 500
        assert "Internal error" in exc_info.value.detail


@pytest.mark.asyncio
async def test_routing_health_uninitialized() -> None:
    with patch("src.main.app.state.guna_router", None, create=True):
        res = await routing_health()
        assert res["guna_router_initialized"] is False
        assert res["tamasic_layer"] == "available"


@pytest.mark.asyncio
async def test_routing_health_initialized_healthy() -> None:
    mock_guna = MagicMock()
    mock_guna.rajasic.embedder.health_check = AsyncMock(return_value=True)
    mock_guna.rajasic.embedder.model = "nomic-embed-text"

    with patch("src.main.app.state.guna_router", mock_guna, create=True):
        res = await routing_health()
        assert res["guna_router_initialized"] is True
        assert res["rajasic_layer"] == "healthy"
        assert res["ollama_model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_routing_health_error() -> None:
    with patch("src.main.app.state", side_effect=RuntimeError("State corrupted")):
        res = await routing_health()
        assert res == {"status": "error", "message": "Internal error"}
