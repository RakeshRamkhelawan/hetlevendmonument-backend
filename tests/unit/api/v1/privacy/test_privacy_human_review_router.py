import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from fastapi import HTTPException, Request

from src.core.api.v1.privacy.human_review_router import (
    human_review_router,
    request_human_review,
    get_human_review_requests,
    HumanReviewRequestPayload,
)
from src.core.models.rbac_models import User
from tests.helpers.limiet_request import echte_request


def test_routes_registered() -> None:
    paths = [r.path for r in human_review_router.routes]
    assert "/human-review" in paths
    assert "/human-review-requests" in paths


@pytest.mark.asyncio
async def test_request_human_review_success() -> None:
    user = MagicMock(spec=User)
    user.id = 42
    db = MagicMock()
    req = echte_request()
    payload = HumanReviewRequestPayload(decision_id=101, reason="Needs second opinion")

    with patch("src.core.api.v1.privacy.human_review_router.AITransparencyService") as mock_svc_cls:
        svc = MagicMock()
        mock_review = MagicMock()
        mock_review.review_id = "rev-999"
        mock_review.status = "pending"
        mock_review.estimated_resolution_days = 3
        mock_review.user_rights = ["appeal", "explanation"]
        svc.request_human_review = AsyncMock(return_value=mock_review)
        mock_svc_cls.return_value = svc

        res = await request_human_review(
            request=req,
            review_request=payload,
            current_user=user,
            db=db,
        )
        assert res["status"] == "success"
        assert res["review_id"] == "rev-999"
        assert res["review_status"] == "pending"


@pytest.mark.asyncio
async def test_request_human_review_error() -> None:
    user = MagicMock(spec=User)
    user.id = 42
    db = MagicMock()
    req = echte_request()
    payload = HumanReviewRequestPayload(decision_id=101, reason="Test")

    with patch("src.core.api.v1.privacy.human_review_router.AITransparencyService") as mock_svc_cls:
        svc = MagicMock()
        svc.request_human_review = AsyncMock(side_effect=RuntimeError("Service error"))
        mock_svc_cls.return_value = svc

        with pytest.raises(HTTPException) as exc_info:
            await request_human_review(
                request=req,
                review_request=payload,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 500
        assert "Failed to request human review" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_human_review_requests_success() -> None:
    user = MagicMock(spec=User)
    user.id = 42
    db = MagicMock()
    req = echte_request()
    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 1

    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.decision_id = "101"
    mock_item.reason = "Test reason"
    mock_item.status = "pending"
    mock_item.reviewer_notes = None
    mock_item.created_at = datetime.now(timezone.utc)
    mock_item.reviewed_at = None

    mock_items_res = MagicMock()
    mock_items_res.scalars().all.return_value = [mock_item]

    db.execute = AsyncMock(side_effect=[mock_count_res, mock_items_res])

    res = await get_human_review_requests(
        request=req,
        limit=50,
        offset=0,
        current_user=user,
        db=db,
    )
    assert res["total_count"] == 1
    assert len(res["requests"]) == 1
    assert res["requests"][0]["decision_id"] == "101"
