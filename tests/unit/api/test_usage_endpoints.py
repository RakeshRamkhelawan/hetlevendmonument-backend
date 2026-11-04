import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.usage_endpoints import router, get_usage_status, record_manual_usage


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/usage/status" in paths
    assert "/usage/record" in paths


@pytest.mark.asyncio
async def test_get_usage_status_free_tier() -> None:
    current_user = MagicMock()
    current_user.tenant_id = "tenant-123"
    current_user.subscription_tier = "free"
    db = MagicMock()

    with patch("src.core.api.usage_endpoints.UsageService") as mock_cls:
        svc = MagicMock()
        svc.get_monthly_usage = AsyncMock(side_effect=[15, 250])
        mock_cls.return_value = svc

        res = await get_usage_status(current_user=current_user, db=db)
        assert "workflow_run" in res
        assert res["workflow_run"]["used"] == 15
        assert res["workflow_run"]["limit"] == 50
        assert res["workflow_run"]["unit"] == "executions"
        assert res["ai_token"]["used"] == 250
        assert res["ai_token"]["limit"] == 50
        assert res["ai_token"]["unit"] == "tokens"


@pytest.mark.asyncio
async def test_get_usage_status_pro_tier() -> None:
    current_user = MagicMock()
    current_user.tenant_id = "tenant-pro"
    current_user.subscription_tier = "pro"
    db = MagicMock()

    with patch("src.core.api.usage_endpoints.UsageService") as mock_cls:
        svc = MagicMock()
        svc.get_monthly_usage = AsyncMock(side_effect=[120, 8000])
        mock_cls.return_value = svc

        res = await get_usage_status(current_user=current_user, db=db)
        assert res["workflow_run"]["limit"] == 10000
        assert res["ai_token"]["limit"] == 10000


@pytest.mark.asyncio
async def test_record_manual_usage_success() -> None:
    current_user = MagicMock()
    current_user.tenant_id = "tenant-123"
    current_user.id = 42
    db = MagicMock()

    with patch("src.core.api.usage_endpoints.UsageService") as mock_cls:
        svc = MagicMock()
        svc.record_usage = AsyncMock(return_value=True)
        mock_cls.return_value = svc

        res = await record_manual_usage(
            metric_type="workflow_run",
            value=2.0,
            current_user=current_user,
            db=db,
        )
        assert res == {"status": "success"}
        svc.record_usage.assert_awaited_once_with(
            tenant_id="tenant-123",
            user_id=42,
            metric_type="workflow_run",
            value=2.0,
        )


@pytest.mark.asyncio
async def test_record_manual_usage_failure() -> None:
    current_user = MagicMock()
    current_user.tenant_id = "tenant-123"
    current_user.id = 42
    db = MagicMock()

    with patch("src.core.api.usage_endpoints.UsageService") as mock_cls:
        svc = MagicMock()
        svc.record_usage = AsyncMock(return_value=False)
        mock_cls.return_value = svc

        with pytest.raises(HTTPException) as exc_info:
            await record_manual_usage(
                metric_type="ai_token",
                value=50.0,
                current_user=current_user,
                db=db,
            )
        assert exc_info.value.status_code == 500
        assert "Failed to record usage" in exc_info.value.detail
