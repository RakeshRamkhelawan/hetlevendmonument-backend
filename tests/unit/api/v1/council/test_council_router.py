"""Unit tests for council router (src/core/api/v1/council/router.py).

Covers:
- GET /api/v1/council/decisions
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.council.router import (
    _derive_risk_level,
    list_council_decisions,
    router,
)


class DummyTicket:
    def __init__(self) -> None:
        self.ticket_ref = "ticket-123"
        self.agent_id = "agent-legal"
        self.risk_factors = ["HIGH_RISK_PII", "CRITICAL_ACTION"]
        self.requested_at = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
        self.reason = "Need approval to process sensitive data"


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/api/v1/council/decisions" in paths


def test_derive_risk_level() -> None:
    assert _derive_risk_level(["critical_factor"]) == "critical"
    assert _derive_risk_level(["high_factor"]) == "high"
    assert _derive_risk_level(["pii_leak"]) == "medium"
    assert _derive_risk_level(["standard"]) == "low"


@pytest.mark.asyncio
async def test_list_council_decisions_unsupported_status_returns_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await list_council_decisions(status="approved", repo=AsyncMock())
    assert exc_info.value.status_code == 400
    assert "Only status=pending is supported" in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_council_decisions_success() -> None:
    repo = AsyncMock()
    repo.list_pending_hitl_requests.return_value = [DummyTicket()]

    res = await list_council_decisions(status="pending", limit=10, offset=0, repo=repo)
    assert len(res.decisions) == 1
    d = res.decisions[0]
    assert d.id == "ticket-123"
    assert d.agent_id == "agent-legal"
    assert d.risk_level == "critical"
    assert d.description == "Need approval to process sensitive data"
