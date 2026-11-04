"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
GDPR DSAR sub-router (ADR-033 Laag 1).

Routes:
- GET /report/gdpr/dsar
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
from src.core.api.v1.compliance.schemas import DSARReportResponse, DSARRequestItem
from src.core.models.rbac_models import User

gdpr_dsar_router = APIRouter()


@gdpr_dsar_router.get(
    "/report/gdpr/dsar",
    response_model=DSARReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get DSAR request report",
    description="""
    Returns a report of Data Subject Access Requests (DSAR) for the tenant.

    Query parameters:
    - days: Number of days to include (1-365, default: 30)
    - status: Filter by status (all, pending, completed, overdue)

    Requires authentication.
    """,
    responses={
        status.HTTP_200_OK: {
            "description": "DSAR report retrieved successfully",
            "model": DSARReportResponse,
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid query parameters"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
@governance_read_limit
async def get_dsar_report(
    request: Request,
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days to include in the report (1-365)",
    ),
    status_filter: str = Query(
        default="all",
        pattern="^(all|pending|completed|overdue)$",
        description="Filter by DSAR status (all, pending, completed, overdue)",
    ),
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    svc: ComplianceAggregationService = Depends(get_aggregation_service),
) -> DSARReportResponse:
    """Get DSAR request report for the authenticated tenant."""
    tenant_id = current_user.tenant_id

    logger.info(
        "Fetching DSAR report",
        tenant_id=tenant_id,
        user_id=current_user.id,
        days=days,
        status_filter=status_filter,
    )

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        dsar_requests = await svc.get_dsar_requests(tenant_id=tenant_id, since=cutoff_date)

        request_items = []
        by_status: dict[str, int] = {"pending": 0, "completed": 0, "overdue": 0}

        overdue_threshold = datetime.now(timezone.utc) - timedelta(days=30)

        for req in dsar_requests:
            effective_status = req.status
            if req.status == "pending" and req.requested_at < overdue_threshold:
                effective_status = "overdue"

            if status_filter != "all" and effective_status != status_filter:
                continue

            if req.completed_at and req.requested_at:
                response_time = (req.completed_at - req.requested_at).total_seconds() / 3600
            else:
                response_time = 0.0

            item = DSARRequestItem(
                id=str(req.id),
                type=req.request_type,
                status=effective_status,
                requested_at=req.requested_at.isoformat() if req.requested_at else "",
                completed_at=req.completed_at.isoformat() if req.completed_at else None,
                response_time_hours=response_time,
                data_subject_id=req.user_id,
            )
            request_items.append(item)
            by_status[effective_status] = by_status.get(effective_status, 0) + 1

        logger.info(
            "DSAR report retrieved successfully",
            tenant_id=tenant_id,
            count=len(request_items),
            by_status=by_status,
        )

        total_count = len(request_items)
        paginated_items = request_items[offset : offset + limit]

        return DSARReportResponse(
            requests=paginated_items,
            count=len(paginated_items),
            by_status=by_status,
            period_days=days,
            limit=limit,
            offset=offset,
            total_count=total_count,
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve DSAR report: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            tenant_id=tenant_id,
            days=days,
            status_filter=status_filter,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve DSAR report",
        )
