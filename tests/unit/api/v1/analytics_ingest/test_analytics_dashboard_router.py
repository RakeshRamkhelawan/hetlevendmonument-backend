import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.analytics_ingest.dashboard_router import router, get_dashboard_stats
from src.core.api.v1.analytics_ingest.dependencies import UserResponse
from src.core.api.v1.analytics_ingest.schemas import DashboardStatsResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/dashboard" in paths


@pytest.mark.asyncio
async def test_get_dashboard_stats_success() -> None:
    user = UserResponse(id=1, email="test@example.com", tenant_id="42", role="user")

    session = AsyncMock()
    # 1. workflow_result (count)
    res_wf_count = MagicMock()
    res_wf_count.scalar.return_value = 5

    # 2. templates_result (scalars all)
    mock_tmpl = MagicMock()
    mock_tmpl.id = 1
    mock_tmpl.name = "Support Bot"
    mock_tmpl.description = "Automated support"
    res_tmpl = MagicMock()
    res_tmpl.scalars.return_value.all.return_value = [mock_tmpl]

    # 3. total_exec_result (count)
    res_exec_count = MagicMock()
    res_exec_count.scalar.return_value = 10

    # 4. failed_result (count)
    res_failed_count = MagicMock()
    res_failed_count.scalar.return_value = 1

    session.execute.side_effect = [res_wf_count, res_tmpl, res_exec_count, res_failed_count]

    resp = await get_dashboard_stats(
        db=session,
        current_user=user,
        tenant_id=42,
    )

    assert isinstance(resp, DashboardStatsResponse)
    assert resp.workflows.totalWorkflows == 10
    assert resp.workflows.failureCount == 1
    assert resp.workflows.successRate == 90.0
    assert len(resp.quickTemplates) == 1
    assert resp.quickTemplates[0].name == "Support Bot"
    assert len(resp.quota) == 3
    assert resp.quota[0].used == 5.0
