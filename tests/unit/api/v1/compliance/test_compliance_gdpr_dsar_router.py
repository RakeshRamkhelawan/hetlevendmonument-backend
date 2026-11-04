import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.compliance.gdpr_dsar_router import gdpr_dsar_router, get_dsar_report
from src.core.api.v1.compliance.schemas import DSARReportResponse
from src.core.models.rbac_models import User
from tests.helpers.limiet_request import echte_request


def test_routes_registered() -> None:
    paths = [r.path for r in gdpr_dsar_router.routes]
    assert "/report/gdpr/dsar" in paths


@pytest.mark.asyncio
async def test_get_dsar_report_success() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = 42

    now = datetime.now(timezone.utc)
    mock_item = MagicMock()
    mock_item.id = 101
    mock_item.request_type = "access"
    mock_item.status = "completed"
    mock_item.requested_at = now
    mock_item.completed_at = now
    mock_item.user_id = "555"

    svc = AsyncMock()
    svc.get_dsar_requests.return_value = [mock_item]

    req = echte_request()
    resp = await get_dsar_report(
        request=req,
        days=30,
        status_filter="all",
        limit=50,
        offset=0,
        current_user=user,
        svc=svc,
    )

    assert isinstance(resp, DSARReportResponse)
    assert resp.count == 1
    assert resp.total_count == 1
    assert resp.by_status["completed"] == 1
    assert resp.requests[0].id == "101"
    assert resp.requests[0].type == "access"
