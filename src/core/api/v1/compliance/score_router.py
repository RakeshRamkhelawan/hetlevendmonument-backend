"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
Compliance Score sub-router (ADR-033 Laag 1).

Routes:
- GET /score
- GET /score/history
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from src.core.api.v1.compliance.schemas import (
    ComplianceScoreHistoryResponse,
    ComplianceScoreResponse,
)
from src.core.api.v1.compliance.dependencies import (
    ComplianceScoreCalculator,
    ComplianceScoreResult,
    get_current_user,
    get_score_service,
    governance_read_limit,
)
from src.core.models.rbac_models import User

score_router = APIRouter()


@score_router.get(
    "/score",
    response_model=ComplianceScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current compliance score",
    description="""
    Returns the current compliance score for the authenticated tenant.

    Scores include:
    - overall_score: Weighted average (GDPR 40%, AI Act 35%, Audit 25%)
    - gdpr_score: GDPR compliance metrics
    - ai_act_score: EU AI Act compliance metrics
    - audit_score: Audit log integrity metrics

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "Compliance scores retrieved successfully",
            "model": ComplianceScoreResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_compliance_score(
    request: Request,
    current_user: User = Depends(get_current_user),
    calculator: ComplianceScoreCalculator = Depends(get_score_service),
) -> ComplianceScoreResponse:
    """Get current compliance score for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching compliance score",
        tenant_id=tenant_id,
        user_id=current_user.id,
    )

    try:
        result: ComplianceScoreResult = await calculator.calculate_overall_score(
            tenant_id=tenant_id
        )

        logger.info(
            "Compliance score calculated successfully",
            tenant_id=tenant_id,
            overall_score=result.overall_score,
        )

        return ComplianceScoreResponse(
            overall_score=result.overall_score,
            gdpr_score=result.gdpr_score,
            ai_act_score=result.ai_act_score,
            audit_score=result.audit_score,
            calculated_at=result.calculated_at,
            tenant_id=result.tenant_id,
        )

    except Exception as e:
        logger.error(
            "Failed to calculate compliance score: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate compliance score",
        )


@score_router.get(
    "/score/history",
    response_model=ComplianceScoreHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get compliance score history",
    description="""
    Returns historical compliance scores for the authenticated tenant.

    Query parameters:
    - days: Number of days of history to retrieve (1-365, default: 30)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "Compliance score history retrieved successfully",
            "model": ComplianceScoreHistoryResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid query parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_compliance_score_history(
    request: Request,
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days of history to retrieve (1-365)",
    ),
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    calculator: ComplianceScoreCalculator = Depends(get_score_service),
) -> ComplianceScoreHistoryResponse:
    """Get historical compliance scores for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching compliance score history",
        tenant_id=tenant_id,
        user_id=current_user.id,
        days=days,
    )

    try:
        history_results: list[ComplianceScoreResult] = await calculator.get_score_history(
            tenant_id=tenant_id, days=days
        )

        logger.info(
            "Compliance score history retrieved successfully",
            tenant_id=tenant_id,
            count=len(history_results),
            days_requested=days,
        )

        history_items = [
            ComplianceScoreResponse(
                overall_score=result.overall_score,
                gdpr_score=result.gdpr_score,
                ai_act_score=result.ai_act_score,
                audit_score=result.audit_score,
                calculated_at=result.calculated_at,
                tenant_id=result.tenant_id,
            )
            for result in history_results
        ]

        total_count = len(history_items)
        paginated_items = history_items[offset : offset + limit]

        return ComplianceScoreHistoryResponse(
            history=paginated_items,
            count=len(paginated_items),
            days_requested=days,
            limit=limit,
            offset=offset,
            total_count=total_count,
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve compliance score history: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            days_requested=days,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve compliance score history",
        )
