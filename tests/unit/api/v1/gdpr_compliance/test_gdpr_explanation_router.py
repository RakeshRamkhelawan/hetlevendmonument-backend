"""Unit tests for GDPR decision explanation router (src/core/api/v1/gdpr_compliance/explanation_router.py).

Covers:
- GET /api/gdpr/decisions/{decision_id}/explanation
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.gdpr_compliance.explanation_router import (
    get_decision_explanation,
    router,
)


class DummyUser:
    def __init__(self, id: str = "user-1") -> None:
        self.id = id


class DummyDecision:
    def __init__(self, user_id: str = "user-1", tenant_id: int = 42) -> None:
        self.id = 55
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.decision_type = "automated_loan_assessment"
        self.agent_id = "agent_underwriter"
        self.explanation = "Approved based on credit criteria"
        self.confidence_score = 0.92
        self.profiling_involved = True
        self.human_review_available = True
        self.human_review_requested = False
        self.created_at = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/api/gdpr/decisions/{decision_id}/explanation" in paths


@pytest.mark.asyncio
async def test_get_decision_explanation_invalid_tenant_raises_403() -> None:
    user = DummyUser(id="user-1")
    with pytest.raises(HTTPException) as exc_info:
        await get_decision_explanation(
            decision_id=55,
            db=AsyncMock(),
            current_user=user,
            tenant_id="not-an-int",
        )
    assert exc_info.value.status_code == 403
    assert "Invalid tenant context" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_decision_explanation_not_found_raises_404() -> None:
    user = DummyUser(id="user-1")
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await get_decision_explanation(
            decision_id=999,
            db=db,
            current_user=user,
            tenant_id="42",
        )
    assert exc_info.value.status_code == 404
    assert "AI decision not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_decision_explanation_intra_tenant_ownership_check_403() -> None:
    user = DummyUser(id="attacker-user")
    decision = DummyDecision(user_id="legitimate-owner", tenant_id=42)

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = decision
    db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await get_decision_explanation(
            decision_id=55,
            db=db,
            current_user=user,
            tenant_id="42",
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_decision_explanation_success() -> None:
    user = DummyUser(id="user-1")
    decision = DummyDecision(user_id="user-1", tenant_id=42)

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = decision
    db.execute.return_value = mock_res

    res = await get_decision_explanation(
        decision_id=55,
        db=db,
        current_user=user,
        tenant_id="42",
    )
    assert res["success"] is True
    assert res["data"]["decision_id"] == 55
    assert res["data"]["agent_id"] == "agent_underwriter"
    assert res["data"]["confidence_score"] == 0.92
    assert res["data"]["eu_ai_act"]["article"] == "Art. 13/86"
