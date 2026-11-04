# orphan:exempt reason: sub-router samengesteld door routing/router.py (ADR-033 Laag 1)
"""Routing API -- decision and feedback endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.core.auth.api_deps import UserResponse, get_current_user
from .dependencies import Department

logger = logging.getLogger(__name__)

router = APIRouter(tags=["routing"])


class RouteRequest(BaseModel):
    """Request to test routing."""

    task: str
    task_description: str = ""
    force_guna: str | None = None  # tamasic, rajasic, sattvic


class RouteResponse(BaseModel):
    """Response from routing test."""

    department: str | None
    guna_used: str
    confidence: float
    prana_cost: int
    reasoning: str
    fallback_used: bool


@router.post("/test", response_model=RouteResponse)
async def test_routing(
    request: RouteRequest,
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> RouteResponse:
    """
    Test the GunaRouter with a task.

    This shows which layer (Tamasic/Rajasic/Sattvic) handles the routing.
    """
    try:
        from src.main import app

        guna_router = getattr(app.state, "guna_router", None)

        if not guna_router:
            raise HTTPException(status_code=503, detail="GunaRouter not initialized")

        result = await guna_router.route(
            task=request.task,
            task_description=request.task_description,
            force_guna=request.force_guna,
        )

        return RouteResponse(
            department=result.department.value if result.department else None,
            guna_used=result.guna_used,
            confidence=result.confidence,
            prana_cost=result.prana_cost,
            reasoning=result.reasoning,
            fallback_used=result.fallback_used,
        )

    except Exception as e:
        logger.error("routing test failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/feedback")
async def report_routing_feedback(
    task: str = Query(..., max_length=500),
    predicted_department: str = Query(..., max_length=100),
    actual_department: str = Query(..., max_length=100),
    success: bool = True,
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, str]:
    """
    Report routing feedback for learning.

    This improves future routing decisions.
    """
    try:
        from src.main import app

        guna_router = getattr(app.state, "guna_router", None)

        if not guna_router:
            raise HTTPException(status_code=503, detail="GunaRouter not initialized")

        try:
            pred_dept = Department(predicted_department)
            actual_dept = Department(actual_department)
        except ValueError as e:
            logger.error("report_routing_feedback mislukt: %s: %s", type(e).__name__, e, exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid department")

        await guna_router.report_outcome(
            task=task,
            predicted_department=pred_dept,
            actual_department=actual_dept,
            guna_used="rajasic",  # Simplified
            success=success,
        )

        return {"message": "Feedback recorded, thank you!"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("routing feedback failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e
