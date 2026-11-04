"""
API endpoints for ML-based tool prediction.
Feature 4: Predictive Tool Suggestions.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["ml-predictions"])


class ToolUsageRecord(BaseModel):
    """Single tool usage record for training."""

    tool_id: str
    timestamp: str  # ISO format
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class TrainRequest(BaseModel):
    """Request body for training the predictor."""

    usage_data: list[ToolUsageRecord]


class TrainResponse(BaseModel):
    """Response from training."""

    status: str
    message: str | None = None
    samples: int | None = None
    tools: int | None = None
    train_accuracy: float | None = None


class PredictRequest(BaseModel):
    """Request body for predictions."""

    history: list[str] = []  # Recent tool IDs used
    top_k: int = 3


class ToolSuggestion(BaseModel):
    """Single tool suggestion."""

    tool_id: str
    confidence: float


class PredictResponse(BaseModel):
    """Response with tool predictions."""

    suggestions: list[ToolSuggestion]


@router.post("/train", response_model=TrainResponse)
async def train_predictor(
    request: TrainRequest, current_user: User = Depends(get_current_user)
) -> TrainResponse:
    """
    Train the tool predictor model for the current tenant.

    Requires at least 10 usage records for training.
    """
    from .dependencies import get_tool_predictor

    predictor = await get_tool_predictor()

    # Convert to dict format expected by predictor
    usage_data = [
        {
            "tool_id": record.tool_id,
            "timestamp": record.timestamp,
            "context": record.context or {},
        }
        for record in request.usage_data
    ]

    result = await predictor.train(current_user.tenant_id, usage_data)

    return TrainResponse(**result)


@router.post("/predict-tools", response_model=PredictResponse)
async def predict_tools(
    request: PredictRequest, current_user: User = Depends(get_current_user)
) -> PredictResponse:
    """
    Get tool predictions based on usage history.

    Returns top-k most likely next tools with confidence scores.
    """
    from .dependencies import get_tool_predictor

    predictor = await get_tool_predictor()

    suggestions = await predictor.predict(
        tenant_id=current_user.tenant_id, history=request.history, top_k=request.top_k
    )

    if not suggestions:
        # No model trained yet - return empty
        return PredictResponse(suggestions=[])

    return PredictResponse(suggestions=[ToolSuggestion(**s) for s in suggestions])


@router.get("/predict-tools", response_model=PredictResponse)
async def predict_tools_get(
    history: str = "",  # Comma-separated tool IDs
    top_k: int = 3,
    current_user: User = Depends(get_current_user),
) -> PredictResponse:
    """
    GET version of predict-tools for simpler integration.

    history: Comma-separated list of recent tool IDs (e.g., "tool1,tool2,tool3")
    """
    from .dependencies import get_tool_predictor

    predictor = await get_tool_predictor()

    history_list = [t.strip() for t in history.split(",") if t.strip()] if history else []

    suggestions = await predictor.predict(
        tenant_id=current_user.tenant_id, history=history_list, top_k=top_k
    )

    return PredictResponse(
        suggestions=[ToolSuggestion(**s) for s in suggestions] if suggestions else []
    )
