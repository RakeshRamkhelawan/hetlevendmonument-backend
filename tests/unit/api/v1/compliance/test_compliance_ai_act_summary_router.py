"""Unit tests for compliance AI Act summary router (src/core/api/v1/compliance/ai_act_summary_router.py).

Covers:
- GET /report/ai-act/summary
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.routing import APIRoute
from starlette.requests import Request

from src.core.api.v1.compliance.ai_act_summary_router import (
    ai_act_summary_router,
    get_ai_act_summary,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


def _create_mock_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/report/ai-act/summary",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_routes_registered() -> None:
    routes = [r for r in ai_act_summary_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/report/ai-act/summary" in paths


@pytest.mark.asyncio
async def test_get_ai_act_summary_success() -> None:
    user = DummyUser(id=1, tenant_id=42)
    req = _create_mock_request()

    svc = AsyncMock()
    mock_summary = MagicMock()
    mock_summary.total_ai_decisions = 50
    mock_summary.high_risk_decisions = 2
    mock_summary.human_oversight_rate = 0.96
    mock_summary.explainability_score = 0.89
    mock_summary.bias_audit_count = 10
    mock_summary.period_days = 30
    mock_summary.tenant_id = 42
    svc.get_ai_act_summary.return_value = mock_summary

    resp = await get_ai_act_summary(
        request=req,
        days=30,
        current_user=user,
        svc=svc,
    )
    svc.get_ai_act_summary.assert_awaited_once_with(tenant_id=42, days=30)
    assert resp.total_ai_decisions == 50
    assert resp.high_risk_decisions == 2
    assert resp.tenant_id == 42
