# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""AI Features -- Predictive Analytics sub-router (ADR-033 Laag 1)."""

from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.ai.predictive_analytics import (
    PredictiveAnalyticsEngine,
    PredictionType,
    TimeHorizon,
)
from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.container import Container
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

router = APIRouter()


class PredictionRequestModel(BaseModel):
    """Request model voor predictions."""

    prediction_type: str = Field(description="Type of prediction")
    time_horizon: str = Field(default="short_term", description="Prediction time horizon")
    context: dict[str, object] = Field(default_factory=dict, description="Prediction context")
    features: dict[str, float] = Field(description="Input features for prediction")


class PredictionResponse(BaseModel):
    """Response model voor predictions."""

    prediction_id: str
    prediction_type: str
    time_horizon: str
    predicted_value: float | str | dict[str, object]
    confidence: float
    uncertainty_bounds: list[float]
    feature_importance: dict[str, float]
    timestamp: str


@router.post("/analytics/predict", response_model=PredictionResponse)
@inject
async def make_prediction(
    request: PredictionRequestModel,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    analytics: PredictiveAnalyticsEngine = Depends(Provide[Container.predictive_analytics]),
) -> PredictionResponse:
    """
    Make a predictive analytics prediction.
    Requires: READ permission (USER level).
    """
    try:
        logger.info(
            "User %s requesting prediction: type=%s, horizon=%s",
            current_user.id,
            request.prediction_type,
            request.time_horizon,
        )

        prediction = await analytics.predict(
            prediction_type=PredictionType(request.prediction_type),
            time_horizon=TimeHorizon(request.time_horizon),
            context=request.context,
            features=request.features,
        )

        return PredictionResponse(
            prediction_id=prediction.prediction_id,
            prediction_type=request.prediction_type,
            time_horizon=request.time_horizon,
            predicted_value=prediction.predicted_value,
            confidence=prediction.confidence,
            uncertainty_bounds=prediction.uncertainty_bounds,
            feature_importance=prediction.feature_importance,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.exception("Error making prediction: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to make prediction",
        ) from e
