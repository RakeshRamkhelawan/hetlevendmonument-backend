import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.compliance.ai_act_decisions_router import ai_act_decisions_router, get_ai_act_decisions
from src.core.api.v1.compliance.schemas import AIActDecisionsReportResponse
from src.core.models.rbac_models import User
from tests.helpers.limiet_request import echte_request


def test_routes_registered() -> None:
    paths = [r.path for r in ai_act_decisions_router.routes]
    assert "/report/ai-act/decisions" in paths


@pytest.mark.asyncio
async def test_get_ai_act_decisions_success() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = 42

    now = datetime.now(timezone.utc)
    mock_dec = MagicMock()
    mock_dec.id = 888
    mock_dec.decision_type = "automated_scoring"
    mock_dec.profiling_involved = False
    mock_dec.human_review_requested = True
    mock_dec.confidence_score = 0.92
    mock_dec.created_at = now
    mock_dec.decision_data = {"outcome": "approved"}

    svc = AsyncMock()
    svc.get_ai_decisions.return_value = [mock_dec]

    req = echte_request()
    resp = await get_ai_act_decisions(
        request=req,
        days=30,
        risk_level="all",
        limit=50,
        offset=0,
        current_user=user,
        svc=svc,
    )

    assert isinstance(resp, AIActDecisionsReportResponse)
    assert resp.count == 1
    assert resp.total_count == 1
    assert resp.by_risk_level["medium"] == 1
    assert resp.decisions[0].id == "888"
    assert resp.decisions[0].risk_level == "medium"
    assert resp.decisions[0].human_reviewed is True
    assert resp.decisions[0].explainability_score == 92.0


@pytest.mark.asyncio
async def test_get_ai_act_decisions_filter_by_risk_level() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = 42

    now = datetime.now(timezone.utc)

    # 1. High risk decision (profiling_involved=True)
    dec_high = MagicMock()
    dec_high.id = 101
    dec_high.decision_type = "profiling"
    dec_high.profiling_involved = True
    dec_high.human_review_requested = False
    dec_high.confidence_score = 0.95
    dec_high.created_at = now
    dec_high.decision_data = {"outcome": "flagged"}

    # 2. Medium risk decision (human_review_requested=True)
    dec_medium = MagicMock()
    dec_medium.id = 102
    dec_medium.decision_type = "review"
    dec_medium.profiling_involved = False
    dec_medium.human_review_requested = True
    dec_medium.confidence_score = 0.85
    dec_medium.created_at = now
    dec_medium.decision_data = {"outcome": "pending"}

    # 3. Low risk decision
    dec_low = MagicMock()
    dec_low.id = 103
    dec_low.decision_type = "standard"
    dec_low.profiling_involved = False
    dec_low.human_review_requested = False
    dec_low.confidence_score = 0.99
    dec_low.created_at = now
    dec_low.decision_data = {"outcome": "approved"}

    svc = AsyncMock()
    svc.get_ai_decisions.return_value = [dec_high, dec_medium, dec_low]

    req = echte_request()
    resp = await get_ai_act_decisions(
        request=req,
        days=30,
        risk_level="high",
        limit=50,
        offset=0,
        current_user=user,
        svc=svc,
    )

    assert isinstance(resp, AIActDecisionsReportResponse)
    assert resp.count == 1
    assert resp.total_count == 1
    assert len(resp.decisions) == 1
    assert resp.decisions[0].id == "101"
    assert resp.decisions[0].risk_level == "high"

