"""Unit tests for AI features predictive analytics router (src/core/api/v1/ai_features/analytics_router.py).

Covers:
- POST /analytics/predict
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.routing import APIRoute

from src.core.api.v1.ai_features.analytics_router import (
    PredictionRequestModel,
    make_prediction,
    router,
)
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/analytics/predict" in paths


@pytest.mark.asyncio
async def test_make_prediction_success() -> None:
    user = UserResponse(id=1, email="u@example.com", tenant_id="42", role="user")
    req = PredictionRequestModel(
        prediction_type="resource_demand",
        time_horizon="short_term",
        features={"lead_count": 12.0},
    )

    fake_prediction = MagicMock()
    fake_prediction.prediction_id = "pred-999"
    fake_prediction.predicted_value = 145.5
    fake_prediction.confidence = 0.88
    fake_prediction.uncertainty_bounds = [140.0, 151.0]
    fake_prediction.feature_importance = {"lead_count": 0.9}

    mock_engine = AsyncMock()
    mock_engine.predict.return_value = fake_prediction

    resp = await make_prediction(
        request=req,
        current_user=user,
        _=1,
        analytics=mock_engine,
    )
    assert resp.prediction_id == "pred-999"
    assert resp.predicted_value == 145.5
    assert resp.confidence == 0.88
    assert resp.prediction_type == "resource_demand"
