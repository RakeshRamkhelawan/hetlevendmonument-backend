"""Learning and adaptation API endpoints."""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.agentic.dependencies import (
    AdaptationRuleService,
    LearningAnalyticsService,
    check_learning_health,
    get_adaptation_service,
    get_analytics_service,
    get_db,
)
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.middleware.tenant_context import require_tenant_id

router = APIRouter(prefix="/learning", tags=["Learning & Adaptation"])


# Response Models
class LearningInsightResponse(BaseModel):
    id: str
    category: str | None
    description: str | None
    conversation_id: str
    confidence: float
    created_at: str
    processed: bool
    adaptation_applied: bool


class AdaptationRuleResponse(BaseModel):
    id: str
    rule_type: str
    trigger_keywords: list[str]
    target_supervisor: str | None
    confidence: float
    priority: int
    times_applied: int
    success_rate: float
    active: bool


class FeedbackTrend(BaseModel):
    period: str
    positive_count: int
    negative_count: int
    correction_count: int
    avg_confidence: float


class LearningStats(BaseModel):
    total_insights: int
    active_adaptations: int
    avg_confidence: float
    recent_corrections: int


class CreateAdaptationRequest(BaseModel):
    rule_type: str = Field(..., pattern="^(routing_correction|capability_boost|user_preference)$")
    trigger_keywords: list[str]
    target_supervisor: str
    confidence: float = Field(..., ge=0, le=1)
    priority: int = Field(..., ge=1, le=10)


class AdaptationStats(BaseModel):
    active_rules_count: int
    total_applications: int
    average_success_rate: float
    high_priority_rules: int


# Endpoints
@router.get("/insights", response_model=list[LearningInsightResponse])
async def get_learning_insights(
    category: str | None = None,
    min_confidence: float = 0.0,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[LearningInsightResponse]:
    """Get learning insights from feedback analysis."""
    # Tenant is established via JWT -- no header needed
    insights = [
        LearningInsightResponse(
            id="insight_001",
            category="routing_confusion",
            description="Users frequently ask HR questions with 'payroll' keyword to Finance",
            conversation_id="conv_001",
            confidence=0.88,
            created_at="2026-02-01T00:00:00Z",
            processed=True,
            adaptation_applied=True,
        ),
    ]

    if category:
        insights = [i for i in insights if i.category == category]
    if min_confidence > 0:
        insights = [i for i in insights if i.confidence >= min_confidence]

    return insights[:limit]


@router.get("/insights/{insight_id}", response_model=LearningInsightResponse)
async def get_insight(
    insight_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
) -> LearningInsightResponse:
    """Get a specific learning insight."""
    if insight_id == "insight_001":
        return LearningInsightResponse(
            id=insight_id,
            category="routing_confusion",
            description="Users frequently ask HR questions with 'payroll' keyword to Finance",
            conversation_id="conv_001",
            confidence=0.88,
            created_at="2026-02-01T00:00:00Z",
            processed=True,
            adaptation_applied=True,
        )

    raise HTTPException(status_code=404, detail="Insight not found")


@router.get("/adaptations", response_model=list[AdaptationRuleResponse])
async def get_adaptation_rules(
    active_only: bool = True,
    rule_type: str | None = None,
    min_success_rate: float = 0.0,
    service: AdaptationRuleService = Depends(get_adaptation_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[AdaptationRuleResponse]:
    """Get all adaptation rules from database."""
    tenant_id = str(require_tenant_id())
    try:
        rules = await service.get_active_rules(tenant_id, limit=1000)

        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        if min_success_rate > 0:
            rules = [
                r
                for r in rules
                if r.success_rate is not None and r.success_rate >= min_success_rate
            ]
        if active_only:
            rules = [r for r in rules if r.active]

        return [
            AdaptationRuleResponse(
                id=rule.id or "",
                rule_type=rule.rule_type or "",
                trigger_keywords=rule.trigger_keywords or [],
                target_supervisor=rule.target_supervisor,
                confidence=rule.confidence or 0.0,
                priority=rule.priority or 0,
                times_applied=rule.times_applied or 0,
                success_rate=rule.success_rate or 0.0,
                active=rule.active or False,
            )
            for rule in rules
        ]
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


@router.post("/adaptations", response_model=AdaptationRuleResponse)
async def create_adaptation(
    request: CreateAdaptationRequest,
    service: AdaptationRuleService = Depends(get_adaptation_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> AdaptationRuleResponse:
    """Create a new adaptation rule in database."""
    tenant_id = str(require_tenant_id())
    try:
        rule = await service.create_rule(
            tenant_id=tenant_id,
            rule_type=request.rule_type,
            trigger_keywords=request.trigger_keywords,
            target_supervisor=request.target_supervisor,
            confidence=request.confidence,
            priority=request.priority,
        )

        return AdaptationRuleResponse(
            id=rule.id or "",
            rule_type=rule.rule_type or "",
            trigger_keywords=rule.trigger_keywords or [],
            target_supervisor=rule.target_supervisor,
            confidence=rule.confidence or 0.0,
            priority=rule.priority or 0,
            times_applied=rule.times_applied or 0,
            success_rate=rule.success_rate or 0.0,
            active=rule.active or False,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create rule")


@router.put("/adaptations/{rule_id}/activate")
async def activate_adaptation(
    rule_id: str,
    service: AdaptationRuleService = Depends(get_adaptation_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Activate an adaptation rule."""
    tenant_id = str(require_tenant_id())
    success = await service.activate_rule(rule_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"rule_id": rule_id, "status": "activated", "message": f"Rule {rule_id} is now active"}


@router.put("/adaptations/{rule_id}/deactivate")
async def deactivate_adaptation(
    rule_id: str,
    service: AdaptationRuleService = Depends(get_adaptation_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Deactivate an adaptation rule."""
    tenant_id = str(require_tenant_id())
    success = await service.deactivate_rule(rule_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {
        "rule_id": rule_id,
        "status": "deactivated",
        "message": f"Rule {rule_id} has been deactivated",
    }


@router.get("/adaptations/stats", response_model=AdaptationStats)
async def get_adaptation_stats(
    service: AdaptationRuleService = Depends(get_adaptation_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> AdaptationStats:
    """Get statistics about adaptation rules."""
    tenant_id = str(require_tenant_id())
    stats = await service.get_rule_stats(tenant_id)
    return AdaptationStats(**stats)


@router.get("/trends", response_model=list[FeedbackTrend])
async def get_feedback_trends(
    days: int = Query(30, ge=1, le=365),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[FeedbackTrend]:
    """Get feedback trends over time."""
    return [
        FeedbackTrend(
            period="2026-02-01",
            positive_count=50,
            negative_count=5,
            correction_count=3,
            avg_confidence=0.85,
        ),
        FeedbackTrend(
            period="2026-02-02",
            positive_count=48,
            negative_count=8,
            correction_count=2,
            avg_confidence=0.83,
        ),
    ]


@router.get("/stats", response_model=LearningStats)
async def get_learning_stats(
    service: LearningAnalyticsService = Depends(get_analytics_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> LearningStats:
    """Get learning system statistics."""
    tenant_id = str(require_tenant_id())
    try:
        metrics = await service.get_dashboard_metrics(tenant_id)
        return LearningStats(
            total_insights=metrics.get("insights_pending", 0),
            active_adaptations=metrics.get("active_adaptations", 0),
            avg_confidence=metrics.get("average_rule_confidence", 0.0),
            recent_corrections=0,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get stats")


@router.post("/analyze")
async def trigger_feedback_analysis(
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Trigger feedback analysis to generate new insights."""
    return {"status": "started", "job_id": "analysis_001", "message": "Feedback analysis started"}


@router.get("/patterns")
async def get_learning_patterns(
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detected learning patterns."""
    return {
        "patterns": [
            {
                "type": "keyword_correlation",
                "description": "'VAT' queries often relate to payroll in specific contexts",
                "confidence": 0.78,
                "detected_at": "2026-02-15T00:00:00Z",
            },
            {
                "type": "capability_expansion",
                "description": "Tax agent requests expanding to include VAT queries",
                "confidence": 0.65,
                "detected_at": "2026-02-20T00:00:00Z",
            },
        ]
    }


@router.get("/health")
async def get_learning_health(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get health status of learning services.

    Returns:
        Health report with component statuses
    """
    try:
        health = await check_learning_health(db)
        return health
    except Exception:
        raise HTTPException(status_code=503, detail="Health check failed")
