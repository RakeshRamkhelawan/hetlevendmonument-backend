"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
AI Act Decisions sub-router (ADR-033 Laag 1).

Routes:
- GET /report/ai-act/decisions
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from src.core.api.v1.compliance.dependencies import (
    ComplianceAggregationService,
    get_aggregation_service,
    get_current_user,
    governance_read_limit,
)
from src.core.api.v1.compliance.schemas import AIActDecisionItem, AIActDecisionsReportResponse
from src.core.models.rbac_models import User

ai_act_decisions_router = APIRouter()


@ai_act_decisions_router.get(
    "/report/ai-act/decisions",
    response_model=AIActDecisionsReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI Act decisions report",
    description="""
    Returns a report of AI decisions for the authenticated tenant.

    Query parameters:
    - days: Number of days to include (1-365, default: 30)
    - risk_level: Filter by risk level (all, low, medium, high)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "AI Act decisions report retrieved successfully",
            "model": AIActDecisionsReportResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid query parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_ai_act_decisions(
    request: Request,
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days to include in the report (1-365)",
    ),
    risk_level: str = Query(
        default="all",
        pattern="^(all|low|medium|high)$",
        description="Filter by risk level (all, low, medium, high)",
    ),
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    svc: ComplianceAggregationService = Depends(get_aggregation_service),
) -> AIActDecisionsReportResponse:
    """Get AI Act decisions report for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching AI Act decisions report",
        tenant_id=tenant_id,
        user_id=current_user.id,
        days=days,
        risk_level=risk_level,
    )

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        ai_decisions = await svc.get_ai_decisions(tenant_id=tenant_id, since=cutoff_date)

        decision_items = []
        by_risk_level: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
        human_reviewed_count = 0

        for decision in ai_decisions:
            if decision.profiling_involved:
                decision_risk = "high"
            elif decision.human_review_requested:
                decision_risk = "medium"
            else:
                decision_risk = "low"

            if risk_level != "all" and decision_risk != risk_level:
                continue

            explainability_score = (
                decision.confidence_score * 100 if decision.confidence_score else 0.0
            )

            outcome = "unknown"
            if decision.decision_data and isinstance(decision.decision_data, dict):
                outcome = decision.decision_data.get("outcome", "unknown")

            item = AIActDecisionItem(
                id=str(decision.id),
                decision_type=decision.decision_type,
                risk_level=decision_risk,
                human_reviewed=decision.human_review_requested or False,
                explainability_score=round(explainability_score, 2),
                decided_at=decision.created_at.isoformat() if decision.created_at else "",
                outcome=outcome,
            )
            decision_items.append(item)
            by_risk_level[decision_risk] = by_risk_level.get(decision_risk, 0) + 1

            if decision.human_review_requested:
                human_reviewed_count += 1

        total_decisions = len(decision_items)
        human_oversight_rate = (
            (human_reviewed_count / total_decisions * 100) if total_decisions > 0 else 0.0
        )

        logger.info(
            "AI Act decisions report retrieved successfully",
            tenant_id=tenant_id,
            count=len(decision_items),
            by_risk_level=by_risk_level,
            human_oversight_rate=human_oversight_rate,
        )

        total_count = len(decision_items)
        paginated_items = decision_items[offset : offset + limit]

        paginated_human_reviewed = sum(1 for d in paginated_items if d.human_reviewed)
        paginated_oversight_rate = (
            (paginated_human_reviewed / len(paginated_items) * 100) if paginated_items else 0.0
        )

        return AIActDecisionsReportResponse(
            decisions=paginated_items,
            count=len(paginated_items),
            by_risk_level=by_risk_level,
            human_oversight_rate=round(paginated_oversight_rate, 2),
            period_days=days,
            limit=limit,
            offset=offset,
            total_count=total_count,
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve AI Act decisions report: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            days=days,
            risk_level=risk_level,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI Act decisions report",
        )
