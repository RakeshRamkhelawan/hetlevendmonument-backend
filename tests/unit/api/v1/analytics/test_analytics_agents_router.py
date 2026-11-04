"""Unit tests for agent analytics router (src/core/api/v1/analytics/agents.py).

Covers:
- GET /analytics/agents/{agent_id}/ooda
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.analytics.agents import get_agent_ooda_metrics, router


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/analytics/agents/{agent_id}/ooda" in paths


@pytest.mark.asyncio
async def test_get_agent_ooda_metrics_raises_501_not_implemented() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_agent_ooda_metrics(
            agent_id="agent-007",
            tenant_id=42,
            current_user=object(),
        )
    assert exc_info.value.status_code == 501
    assert exc_info.value.detail["error"]["code"] == "NOT_IMPLEMENTED"
