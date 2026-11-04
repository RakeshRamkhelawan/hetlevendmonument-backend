import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.v1.production.reporting_router import (
    router,
    get_full_production_report,
    get_performance_baseline,
)
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/production-report" in paths
    assert "/performance-baseline" in paths


@pytest.mark.asyncio
async def test_get_full_production_report_success() -> None:
    user = MagicMock(spec=UserResponse)
    user.id = 123

    with patch("src.core.api.v1.production.reporting_router.production_manager") as mock_pm:
        mock_pm.initialize_all_systems = AsyncMock(return_value={"all": "ok"})
        mock_pm.run_comprehensive_test = AsyncMock(return_value={"tests": "passed"})
        mock_pm.generate_production_report = MagicMock(return_value={"status": "ready", "score": 98})

        res = await get_full_production_report(current_user=user, _=1)
        assert res == {"status": "ready", "score": 98}


@pytest.mark.asyncio
async def test_get_full_production_report_error() -> None:
    user = MagicMock(spec=UserResponse)
    user.id = 123

    with patch("src.core.api.v1.production.reporting_router.production_manager") as mock_pm:
        mock_pm.initialize_all_systems = AsyncMock(side_effect=RuntimeError("Init error"))

        with pytest.raises(HTTPException) as exc_info:
            await get_full_production_report(current_user=user, _=1)
        assert exc_info.value.status_code == 500
        assert "Failed to generate production report" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_performance_baseline_success() -> None:
    user = MagicMock(spec=UserResponse)
    user.id = 123

    res = await get_performance_baseline(current_user=user, _=1)
    assert "performance_targets" in res
    assert "current_performance" in res
    assert res["performance_targets"]["max_response_time_ms"] == 100
    assert res["current_performance"]["average_response_time_ms"] == 45.2
