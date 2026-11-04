# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Audit missions sub-router -- list and export mission audit trails.

Migrated from src/core/api/audit_endpoints.py (SP-API-003 Dag 5).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope

from .dependencies import (
    format_csv_export,
    generate_sample_missions,
    get_mission_detail,
    get_tenant,
    get_user_email,
    get_user_id,
)
from .schemas import (
    AuditEvent,
    AuditEventType,
    AuditListResponse,
    ExportFormat,
    GDPRExportMetadata,
    GDPRExportResponse,
    MissionStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/missions",
    response_model=AuditListResponse,
    summary="List missions with audit data",
    description="Lists all missions with comprehensive audit information for the current tenant.",
)
async def list_missions_audit(
    status_filter: MissionStatus | None = Query(None, description="Filter by mission status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.AUDIT_READ)),  # TODO(TYPE): replace Any with concrete type
) -> AuditListResponse:
    """
    List all missions with audit data.

    Returns comprehensive audit information including:
    - Mission summary and status
    - Audit event counts
    - Data categories involved
    - Last activity tracking

    Security: Requires JWT with audit:read scope
    """
    user_id = get_user_id(current_user)

    logger.info(
        "Listing mission audit data",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "status_filter": status_filter.value if status_filter else None,
            "page": page,
            "page_size": page_size,
        },
    )

    # Generate sample data - in production, query database
    all_missions = generate_sample_missions(tenant_id, status_filter)

    # Pagination
    total = len(all_missions)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_missions = all_missions[start_idx:end_idx]
    has_more = end_idx < total

    logger.info(
        "Mission audit list retrieved",
        extra={
            "total_missions": total,
            "returned_count": len(paginated_missions),
            "page": page,
        },
    )

    return AuditListResponse(
        missions=paginated_missions,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        message="Retrieved %d mission(s) with audit data" % len(paginated_missions),
    )


@router.get(
    "/missions/{mission_id}/export",
    summary="GDPR-compliant mission export",
    description="Exports mission data in GDPR-compliant format with full audit trail.",
)
async def export_mission_audit(
    mission_id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    include_processing_records: bool = Query(True, description="Include data processing records"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.AUDIT_READ)),  # TODO(TYPE): replace Any with concrete type
) -> Response:
    """
    Export mission data in GDPR-compliant format.

    Supports multiple formats:
    - **JSON**: Full structured data with metadata
    - **CSV**: Tabular format for spreadsheet analysis
    - **PDF**: Formatted document (simulated)

    Security: Requires JWT with audit:read scope
    """
    user_id = get_user_id(current_user)
    user_email = get_user_email(current_user)
    now = datetime.now(timezone.utc)
    export_id = "export_%s" % uuid.uuid4().hex[:12]

    logger.info(
        "Exporting mission audit data",
        extra={
            "export_id": export_id,
            "mission_id": mission_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "format": format.value,
        },
    )

    # Get mission detail
    mission = get_mission_detail(mission_id, tenant_id)

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission %s not found" % mission_id,
        )

    # Optionally exclude processing records
    if not include_processing_records:
        mission.data_processing = []

    # Add export event to audit trail
    export_event = AuditEvent(
        id="evt_%s" % uuid.uuid4().hex[:8],
        event_type=AuditEventType.EXPORT,
        timestamp=now.isoformat(),
        actor_id=user_id,
        actor_email=user_email,
        details={
            "action": "GDPR data export",
            "format": format.value,
            "export_id": export_id,
        },
        ip_address=None,
        user_agent=None,
    )
    mission.audit_trail.append(export_event)

    # Build export metadata
    metadata = GDPRExportMetadata(
        export_id=export_id,
        exported_at=now.isoformat(),
        exported_by=user_id,
        format=format,
        data_subject_id=None,
        purpose="Data portability / audit compliance",
        legal_basis="GDPR Article 20 - Right to data portability",
        retention_notice="This export should be stored securely and deleted when no longer needed.",
    )

    logger.info(
        "Mission export completed",
        extra={
            "export_id": export_id,
            "mission_id": mission_id,
            "format": format.value,
            "event_count": len(mission.audit_trail),
        },
    )

    # Return based on format
    if format == ExportFormat.CSV:
        csv_content = format_csv_export(mission)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=mission_%s_export.csv" % mission_id
            },
        )
    elif format == ExportFormat.PDF:
        # In production, generate actual PDF
        pdf_placeholder = {
            "notice": "PDF generation simulated for demo",
            "export_id": export_id,
            "mission_id": mission_id,
            "content_type": "application/pdf",
        }
        return JSONResponse(content=pdf_placeholder, headers={"X-Export-Format": "pdf-simulated"})
    else:
        # JSON format (default)
        response = GDPRExportResponse(
            metadata=metadata,
            mission=mission,
            message="GDPR-compliant export generated for mission %s" % mission_id,
            success=True,
        )
        return JSONResponse(
            content=response.model_dump(),
            headers={
                "Content-Disposition": "attachment; filename=mission_%s_export.json" % mission_id
            },
        )
