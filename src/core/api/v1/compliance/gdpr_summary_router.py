"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
GDPR Summary sub-router (ADR-033 Laag 1).

Routes:
- GET /report/gdpr/summary
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
from src.core.api.v1.compliance.schemas import GDPRSummaryResponse
from src.core.models.rbac_models import User

gdpr_summary_router = APIRouter()


@gdpr_summary_router.get(
    "/report/gdpr/summary",
    response_model=GDPRSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get GDPR compliance summary",
    description="""
    Returns a GDPR compliance summary report for the authenticated tenant.

    Query parameters:
    - days: Number of days to include in the report (1-365, default: 30)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "GDPR summary report retrieved successfully",
            "model": GDPRSummaryResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid query parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_gdpr_summary(
    request: Request,
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days to include in the report (1-365)",
    ),
    current_user: User = Depends(get_current_user),
    svc: ComplianceAggregationService = Depends(get_aggregation_service),
) -> GDPRSummaryResponse:
    """Get GDPR compliance summary for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching GDPR summary report",
        tenant_id=tenant_id,
        user_id=current_user.id,
        days=days,
    )

    try:
        service = svc
        summary = await service.get_gdpr_summary(tenant_id=tenant_id, days=days)

        logger.info(
            "GDPR summary report retrieved successfully",
            tenant_id=tenant_id,
            dsar_count=summary.dsar_requests_count,
            data_subjects=summary.total_data_subjects,
        )

        return GDPRSummaryResponse(
            total_data_subjects=summary.total_data_subjects,
            dsar_requests_count=summary.dsar_requests_count,
            dsar_avg_response_time_hours=summary.dsar_avg_response_time_hours,
            consent_records_count=summary.consent_records_count,
            data_retention_violations=summary.data_retention_violations,
            period_days=summary.period_days,
            tenant_id=summary.tenant_id,
            generated_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve GDPR summary report: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            days=days,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve GDPR summary report",
        )
