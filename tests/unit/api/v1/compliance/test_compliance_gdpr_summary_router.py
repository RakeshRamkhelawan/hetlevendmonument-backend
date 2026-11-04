"""Unit tests for compliance GDPR summary router (src/core/api/v1/compliance/gdpr_summary_router.py).

Covers:
- GET /report/gdpr/summary
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.routing import APIRoute
from starlette.requests import Request

from src.core.api.v1.compliance.gdpr_summary_router import (
    gdpr_summary_router,
    get_gdpr_summary,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


def _create_mock_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/report/gdpr/summary",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_routes_registered() -> None:
    routes = [r for r in gdpr_summary_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/report/gdpr/summary" in paths


@pytest.mark.asyncio
async def test_get_gdpr_summary_success() -> None:
    user = DummyUser(id=1, tenant_id=42)
    req = _create_mock_request()

    svc = AsyncMock()
    mock_summary = MagicMock()
    mock_summary.total_data_subjects = 1200
    mock_summary.dsar_requests_count = 5
    mock_summary.dsar_avg_response_time_hours = 24.5
    mock_summary.consent_records_count = 1150
    mock_summary.data_retention_violations = 0
    mock_summary.period_days = 30
    mock_summary.tenant_id = 42
    svc.get_gdpr_summary.return_value = mock_summary

    resp = await get_gdpr_summary(
        request=req,
        days=30,
        current_user=user,
        svc=svc,
    )
    svc.get_gdpr_summary.assert_awaited_once_with(tenant_id=42, days=30)
    assert resp.total_data_subjects == 1200
    assert resp.dsar_requests_count == 5
    assert resp.data_retention_violations == 0
    assert resp.tenant_id == 42
