"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
AI Act Summary sub-router (ADR-033 Laag 1).

Routes:
- GET /report/ai-act/summary
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from src.core.api.v1.compliance.dependencies import (
    ComplianceAggregationService,
    get_aggregation_service,
    get_current_user,
    governance_read_limit,
)
from src.core.api.v1.compliance.schemas import AIActSummaryResponse
from src.core.models.rbac_models import User

ai_act_summary_router = APIRouter()


@ai_act_summary_router.get(
    "/report/ai-act/summary",
    response_model=AIActSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI Act compliance summary",
    description="""
    Returns an AI Act compliance summary report for the authenticated tenant.

    Query parameters:
    - days: Number of days to include in the report (1-365, default: 30)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "AI Act summary report retrieved successfully",
            "model": AIActSummaryResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid query parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_ai_act_summary(
    request: Request,
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days to include in the report (1-365)",
    ),
    current_user: User = Depends(get_current_user),
    svc: ComplianceAggregationService = Depends(get_aggregation_service),
) -> AIActSummaryResponse:
    """Get AI Act compliance summary for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching AI Act summary report",
        tenant_id=tenant_id,
        user_id=current_user.id,
        days=days,
    )

    try:
        service = svc
        summary = await service.get_ai_act_summary(tenant_id=tenant_id, days=days)

        logger.info(
            "AI Act summary report retrieved successfully",
            tenant_id=tenant_id,
            total_decisions=summary.total_ai_decisions,
            high_risk=summary.high_risk_decisions,
        )

        return AIActSummaryResponse(
            total_ai_decisions=summary.total_ai_decisions,
            high_risk_decisions=summary.high_risk_decisions,
            human_oversight_rate=summary.human_oversight_rate,
            explainability_score=summary.explainability_score,
            bias_audit_count=summary.bias_audit_count,
            period_days=summary.period_days,
            tenant_id=summary.tenant_id,
            generated_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve AI Act summary report: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            days=days,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI Act summary report",
        )
