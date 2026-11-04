import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException

from src.core.api.v1.activepieces.health_router import (
    router,
    check_integration_health,
    check_integration_health_detailed,
)


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/integrations/health" in paths
    assert "/integrations/health/detailed" in paths


@pytest.mark.asyncio
async def test_check_integration_health_healthy() -> None:
    service = AsyncMock()
    service.get_detailed_health.return_value = {"is_available": True, "latency_ms": 12}

    res = await check_integration_health(service=service)
    assert res["status"] == "healthy"
    assert res["service"] == "activepieces"
    assert res["details"]["latency_ms"] == 12


@pytest.mark.asyncio
async def test_check_integration_health_unhealthy_raises_503() -> None:
    service = AsyncMock()
    service.get_detailed_health.return_value = {"is_available": False}

    with pytest.raises(HTTPException) as exc_info:
        await check_integration_health(service=service)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_check_integration_health_detailed() -> None:
    service = AsyncMock()
    service.get_detailed_health.return_value = {"is_available": True, "circuit_breaker": "closed"}

    res = await check_integration_health_detailed(service=service)
    assert res["circuit_breaker"] == "closed"
