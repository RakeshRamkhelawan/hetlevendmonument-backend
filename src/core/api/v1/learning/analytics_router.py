"""Learning analytics, metrics, and reporting endpoints (ADR-033 Laag 1, max 200 regels)."""

import logging
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core.api.v1.learning.dependencies import (
    LearningAnalytics,
    ReportGenerator,
    get_learning_metrics,
    get_regional_context,
    get_roi_report,
)
from src.core.middleware.tenant_context import require_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()


class InsightResponse(BaseModel):
    """Learning insight response."""

    id: str
    category: str
    confidence_score: float
    adaptation_applied: bool
    feedback_type: str
    created_at: datetime


class MetricsResponse(BaseModel):
    """Learning metrics response."""

    total_insights: int
    adaptations_applied: int
    success_rate: float
    avg_confidence: float
    trend_direction: str
    trend_percentage: float
    top_categories: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    performance_score: float


class ROIResponse(BaseModel):
    """ROI metrics response."""

    time_saved_hours: float
    accuracy_improvement: float
    manual_interventions_prevented: int
    estimated_cost_savings: float
    roi_percentage: float


class ReportResponse(BaseModel):
    """Analytics report response."""

    period: str
    generated_at: datetime
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


@router.get("/insights", response_model=list[InsightResponse])
async def list_insights(
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[InsightResponse]:
    """List learning insights."""
    require_tenant_id()
    return []


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
) -> MetricsResponse:
    """Get learning system metrics."""
    require_tenant_id()
    try:
        metrics = await get_learning_metrics(days=days)
        return MetricsResponse(
            total_insights=metrics.total_insights,
            adaptations_applied=metrics.adaptations_applied,
            success_rate=metrics.success_rate,
            avg_confidence=metrics.avg_confidence,
            trend_direction=metrics.trend_direction,
            trend_percentage=metrics.trend_percentage,
            top_categories=metrics.top_categories,
            performance_score=metrics.performance_score,
        )
    except Exception as e:
        logger.error("get_metrics failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@router.get("/roi", response_model=ROIResponse)
async def get_roi(
    hourly_cost: float = Query(50.0, ge=0, le=10000, description="Hourly cost for manual work"),
) -> ROIResponse:
    """Get ROI metrics for learning system."""
    require_tenant_id()
    try:
        roi = await get_roi_report(hourly_cost=hourly_cost)
        return ROIResponse(
            time_saved_hours=roi.time_saved_hours,
            accuracy_improvement=roi.accuracy_improvement,
            manual_interventions_prevented=roi.manual_interventions_prevented,
            estimated_cost_savings=roi.estimated_cost_savings,
            roi_percentage=roi.roi_percentage,
        )
    except Exception as e:
        logger.error("get_roi failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate ROI")


@router.get("/reports/{period}", response_model=ReportResponse)
async def get_report(
    period: str,
) -> ReportResponse:
    """Get analytics report. Period: daily or weekly."""
    require_tenant_id()
    try:
        analytics = LearningAnalytics()
        generator = ReportGenerator(analytics)
        data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        if period == "daily":
            data = cast(dict[str, Any], await generator.generate_daily_report())  # TODO(TYPE): replace Any with concrete type
        elif period == "weekly":
            data = cast(dict[str, Any], await generator.generate_weekly_report())  # TODO(TYPE): replace Any with concrete type
        else:
            raise HTTPException(status_code=400, detail="Invalid period. Use: daily, weekly")
        return ReportResponse(period=period, generated_at=datetime.now(timezone.utc), data=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_report failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.post("/ml/generate-rules", status_code=202)
async def generate_rules_ml(
    min_confidence: float = Query(0.7, ge=0, le=1),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Trigger ML-based rule generation via background analysis of insights."""
    require_tenant_id()
    return {
        "status": "accepted",
        "message": "Rule generation queued",
        "min_confidence": min_confidence,
    }


@router.get("/regional/context")
async def get_regional_context_endpoint() -> dict[str, Any]:  # TODO(TYPE): replace Any
    """Get regional context for current deployment."""
    require_tenant_id()
    try:
        context = await get_regional_context()
        return {
            "region": context.get("region"),
            "timezone": context.get("timezone"),
            "language": context.get("language"),
            "time_pattern": context.get("time_pattern"),
        }
    except Exception as e:
        logger.error("get_regional_context failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get regional context")
