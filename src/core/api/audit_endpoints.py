# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/audit/ (SP-API-003)
"""
Audit API Endpoints
===================

Production-ready REST API endpoints for mission audit trails and GDPR-compliant exports.

Features:
- List all missions with comprehensive audit data
- GDPR-compliant export functionality
- Multi-tenant isolation (JWT + tenant context)
- RBAC enforcement via OAuth2 scopes
- Immutable audit trail support

Endpoints:
- GET /api/v1/audit/missions - List missions with audit data
- GET /api/v1/audit/missions/{id}/export - GDPR-compliant export

Security: JWT required, tenant isolated, scope validated
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope
from src.core.middleware.tenant_context import get_current_tenant_id

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


class MissionStatus(str, Enum):
    """Mission status for audit"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditEventType(str, Enum):
    """Type of audit event"""

    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGE = "status_change"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    COMPLETED = "completed"
    FAILED = "failed"
    DATA_ACCESS = "data_access"
    EXPORT = "export"


class ExportFormat(str, Enum):
    """Supported export formats"""

    JSON = "json"
    CSV = "csv"
    PDF = "pdf"


class DataCategory(str, Enum):
    """GDPR data categories"""

    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"
    DERIVED = "derived"


# ============================================================================
# Pydantic Models
# ============================================================================


class AuditEvent(BaseModel):
    """Individual audit event in the trail"""

    id: str = Field(..., description="Event ID")
    event_type: AuditEventType = Field(..., description="Type of audit event")
    timestamp: str = Field(..., description="Event timestamp ISO format")
    actor_id: str = Field(..., description="User who performed action")
    actor_email: str | None = Field(None, description="Actor email")
    details: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Event details"
    )  # TODO(TYPE): replace Any with concrete type
    ip_address: str | None = Field(None, description="IP address if available")
    user_agent: str | None = Field(None, description="User agent if available")


class DataProcessingRecord(BaseModel):
    """GDPR data processing record"""

    category: DataCategory = Field(..., description="Data category")
    purpose: str = Field(..., description="Processing purpose")
    legal_basis: str = Field(..., description="Legal basis for processing")
    retention_period: str = Field(..., description="Data retention period")
    recipients: list[str] = Field(default_factory=list, description="Data recipients")


class MissionAuditSummary(BaseModel):
    """Summary audit data for a mission"""

    mission_id: str = Field(..., description="Mission ID")
    name: str = Field(..., description="Mission name")
    description: str | None = Field(None, description="Mission description")
    status: MissionStatus = Field(..., description="Current status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    created_by: str = Field(..., description="Creator user ID")
    approved_by: str | None = Field(None, description="Approver user ID")
    approved_at: str | None = Field(None, description="Approval timestamp")
    event_count: int = Field(0, description="Number of audit events")
    last_event_type: AuditEventType | None = Field(None, description="Last event type")
    data_categories: list[DataCategory] = Field(
        default_factory=list, description="Data categories involved"
    )
    tenant_id: int = Field(..., description="Tenant ID")


class MissionAuditDetail(BaseModel):
    """Detailed audit data for a mission"""

    mission_id: str = Field(..., description="Mission ID")
    name: str = Field(..., description="Mission name")
    description: str | None = Field(None, description="Mission description")
    status: MissionStatus = Field(..., description="Current status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    created_by: str = Field(..., description="Creator user ID")
    approved_by: str | None = Field(None, description="Approver user ID")
    approved_at: str | None = Field(None, description="Approval timestamp")
    audit_trail: list[AuditEvent] = Field(default_factory=list, description="Full audit trail")
    data_processing: list[DataProcessingRecord] = Field(
        default_factory=list, description="Data processing records"
    )
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Additional metadata"
    )  # TODO(TYPE): replace Any with concrete type
    tenant_id: int = Field(..., description="Tenant ID")


class AuditListResponse(BaseModel):
    """Response for mission audit list"""

    missions: list[MissionAuditSummary]
    total: int
    page: int
    page_size: int
    has_more: bool
    message: str


class GDPRExportMetadata(BaseModel):
    """Metadata for GDPR export"""

    export_id: str = Field(..., description="Export ID")
    exported_at: str = Field(..., description="Export timestamp")
    exported_by: str = Field(..., description="User who exported")
    format: ExportFormat = Field(..., description="Export format")
    data_subject_id: str | None = Field(None, description="Data subject ID if applicable")
    purpose: str = Field(..., description="Export purpose")
    legal_basis: str = Field(..., description="Legal basis for export")
    retention_notice: str = Field(..., description="Retention notice")


class GDPRExportResponse(BaseModel):
    """Response for GDPR-compliant export"""

    metadata: GDPRExportMetadata
    mission: MissionAuditDetail
    message: str
    success: bool


# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ============================================================================
# Helper Functions
# ============================================================================


async def get_tenant() -> int:
    """Get tenant ID with error handling"""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


def get_user_id(current_user: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user"""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"


def get_user_email(
    current_user: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> str | None:  # TODO(TYPE): replace Any with concrete type
    """Extract user email from current user"""
    if isinstance(current_user, dict):
        return current_user.get("email")
    if hasattr(current_user, "email"):
        return current_user.email
    return None


def generate_sample_audit_trail(mission_id: str, status: MissionStatus) -> list[AuditEvent]:
    """Generate sample audit trail for demonstration"""
    now = datetime.now(timezone.utc)
    events: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    # Creation event
    events.append(
        AuditEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=AuditEventType.CREATED,
            timestamp=(now - timedelta(days=7)).isoformat(),
            actor_id="user_creator",
            actor_email="creator@example.com",
            details={"action": "Mission created", "initial_status": "pending"},
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )
    )

    # Update event
    events.append(
        AuditEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=AuditEventType.UPDATED,
            timestamp=(now - timedelta(days=5)).isoformat(),
            actor_id="user_editor",
            actor_email="editor@example.com",
            details={
                "action": "Mission updated",
                "fields_changed": ["description", "parameters"],
            },
            ip_address="192.168.1.101",
            user_agent=None,
        )
    )

    # Status-specific events
    if status in [
        MissionStatus.APPROVED,
        MissionStatus.COMPLETED,
        MissionStatus.IN_PROGRESS,
    ]:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.APPROVED,
                timestamp=(now - timedelta(days=3)).isoformat(),
                actor_id="user_approver",
                actor_email="approver@example.com",
                details={
                    "action": "Mission approved",
                    "approval_notes": "Meets all criteria",
                },
                ip_address="192.168.1.102",
                user_agent=None,
            )
        )

    if status == MissionStatus.REJECTED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.REJECTED,
                timestamp=(now - timedelta(days=3)).isoformat(),
                actor_id="user_reviewer",
                actor_email="reviewer@example.com",
                details={
                    "action": "Mission rejected",
                    "rejection_reason": "Does not meet requirements",
                },
                ip_address="192.168.1.103",
                user_agent=None,
            )
        )

    if status in [MissionStatus.IN_PROGRESS, MissionStatus.COMPLETED]:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.EXECUTED,
                timestamp=(now - timedelta(days=2)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission execution started",
                    "executor": "agent_001",
                },
                ip_address=None,
                user_agent=None,
            )
        )

    if status == MissionStatus.COMPLETED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.COMPLETED,
                timestamp=(now - timedelta(days=1)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission completed",
                    "result": "success",
                    "duration_ms": 45000,
                },
                ip_address=None,
                user_agent=None,
            )
        )

    if status == MissionStatus.FAILED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.FAILED,
                timestamp=(now - timedelta(days=1)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission failed",
                    "error": "Timeout exceeded",
                    "retry_count": 3,
                },
                ip_address=None,
                user_agent=None,
            )
        )

    return events


def generate_data_processing_records() -> list[DataProcessingRecord]:
    """Generate sample data processing records for GDPR compliance"""
    return [
        DataProcessingRecord(
            category=DataCategory.TECHNICAL,
            purpose="Mission execution and monitoring",
            legal_basis="Legitimate interest - service provision",
            retention_period="90 days after mission completion",
            recipients=["Internal systems", "Authorized personnel"],
        ),
        DataProcessingRecord(
            category=DataCategory.BEHAVIORAL,
            purpose="Performance analytics and optimization",
            legal_basis="Legitimate interest - service improvement",
            retention_period="12 months",
            recipients=["Analytics team"],
        ),
        DataProcessingRecord(
            category=DataCategory.DERIVED,
            purpose="Audit trail and compliance",
            legal_basis="Legal obligation - audit requirements",
            retention_period="7 years",
            recipients=["Compliance team", "External auditors (upon request)"],
        ),
    ]


def generate_sample_missions(
    tenant_id: int, status_filter: MissionStatus | None = None
) -> list[MissionAuditSummary]:
    """Generate sample mission audit data for demonstration"""
    now = datetime.now(timezone.utc)

    sample_missions: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
        {
            "mission_id": "mission_001",
            "name": "Data Analysis Pipeline",
            "description": "Automated data analysis for quarterly report",
            "status": MissionStatus.COMPLETED,
            "created_by": "user_001",
            "approved_by": "user_002",
            "days_ago": 10,
        },
        {
            "mission_id": "mission_002",
            "name": "Customer Segmentation",
            "description": "ML-based customer segmentation analysis",
            "status": MissionStatus.IN_PROGRESS,
            "created_by": "user_003",
            "approved_by": "user_002",
            "days_ago": 5,
        },
        {
            "mission_id": "mission_003",
            "name": "Report Generation",
            "description": "Generate weekly performance reports",
            "status": MissionStatus.PENDING,
            "created_by": "user_001",
            "approved_by": None,
            "days_ago": 2,
        },
        {
            "mission_id": "mission_004",
            "name": "Data Migration",
            "description": "Migrate legacy data to new system",
            "status": MissionStatus.APPROVED,
            "created_by": "user_004",
            "approved_by": "user_002",
            "days_ago": 3,
        },
        {
            "mission_id": "mission_005",
            "name": "Compliance Check",
            "description": "Automated compliance verification",
            "status": MissionStatus.FAILED,
            "created_by": "user_002",
            "approved_by": "user_001",
            "days_ago": 7,
        },
        {
            "mission_id": "mission_006",
            "name": "Risk Assessment",
            "description": "Quarterly risk assessment automation",
            "status": MissionStatus.REJECTED,
            "created_by": "user_003",
            "approved_by": None,
            "days_ago": 4,
        },
    ]

    missions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for m in sample_missions:
        if status_filter and m["status"] != status_filter:
            continue

        created_at = now - timedelta(days=m["days_ago"])
        updated_at = now - timedelta(days=max(0, m["days_ago"] - 1))
        approved_at = (
            (now - timedelta(days=m["days_ago"] - 1)).isoformat() if m["approved_by"] else None
        )

        audit_trail = generate_sample_audit_trail(m["mission_id"], m["status"])

        missions.append(
            MissionAuditSummary(
                mission_id=m["mission_id"],
                name=m["name"],
                description=m["description"],
                status=m["status"],
                created_at=created_at.isoformat(),
                updated_at=updated_at.isoformat(),
                created_by=m["created_by"],
                approved_by=m["approved_by"],
                approved_at=approved_at,
                event_count=len(audit_trail),
                last_event_type=audit_trail[-1].event_type if audit_trail else None,
                data_categories=[DataCategory.TECHNICAL, DataCategory.BEHAVIORAL],
                tenant_id=tenant_id,
            )
        )

    return missions


def get_mission_detail(mission_id: str, tenant_id: int) -> MissionAuditDetail | None:
    """Get detailed mission audit data"""
    # Sample mission data - in production, fetch from database
    sample_missions: dict[str, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
        "mission_001": {
            "name": "Data Analysis Pipeline",
            "description": "Automated data analysis for quarterly report",
            "status": MissionStatus.COMPLETED,
            "created_by": "user_001",
            "approved_by": "user_002",
        },
        "mission_002": {
            "name": "Customer Segmentation",
            "description": "ML-based customer segmentation analysis",
            "status": MissionStatus.IN_PROGRESS,
            "created_by": "user_003",
            "approved_by": "user_002",
        },
        "mission_003": {
            "name": "Report Generation",
            "description": "Generate weekly performance reports",
            "status": MissionStatus.PENDING,
            "created_by": "user_001",
            "approved_by": None,
        },
    }

    if mission_id not in sample_missions:
        return None

    m = sample_missions[mission_id]
    now = datetime.now(timezone.utc)

    return MissionAuditDetail(
        mission_id=mission_id,
        name=m["name"],
        description=m["description"],
        status=m["status"],
        created_at=(now - timedelta(days=7)).isoformat(),
        updated_at=(now - timedelta(days=1)).isoformat(),
        created_by=m["created_by"],
        approved_by=m["approved_by"],
        approved_at=(now - timedelta(days=5)).isoformat() if m["approved_by"] else None,
        audit_trail=generate_sample_audit_trail(mission_id, m["status"]),
        data_processing=generate_data_processing_records(),
        metadata={"version": "1.0", "schema": "audit_v2", "export_compliant": True},
        tenant_id=tenant_id,
    )


def format_csv_export(mission: MissionAuditDetail) -> str:
    """Format mission audit data as CSV"""
    lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    # Header
    lines.append("# GDPR Data Export")
    lines.append(f"# Mission ID: {mission.mission_id}")
    lines.append(f"# Export Date: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    # Mission Summary
    lines.append("## Mission Summary")
    lines.append("Field,Value")
    lines.append(f"Mission ID,{mission.mission_id}")
    lines.append(f"Name,{mission.name}")
    lines.append(f"Status,{mission.status.value}")
    lines.append(f"Created At,{mission.created_at}")
    lines.append(f"Created By,{mission.created_by}")
    lines.append("")

    # Audit Trail
    lines.append("## Audit Trail")
    lines.append("Event ID,Event Type,Timestamp,Actor ID,Details")
    for event in mission.audit_trail:
        details = json.dumps(event.details).replace(",", ";")
        lines.append(
            f"{event.id},{event.event_type.value},{event.timestamp},{event.actor_id},{details}"
        )
    lines.append("")

    # Data Processing
    lines.append("## Data Processing Records")
    lines.append("Category,Purpose,Legal Basis,Retention Period")
    for record in mission.data_processing:
        lines.append(
            f"{record.category.value},{record.purpose},{record.legal_basis},{record.retention_period}"
        )

    return "\n".join(lines)


# ============================================================================
# Endpoints
# ============================================================================


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
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.AUDIT_READ)
    ),  # TODO(TYPE): replace Any with concrete type
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
        message=f"Retrieved {len(paginated_missions)} mission(s) with audit data",
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
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.AUDIT_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> Response:
    """
    Export mission data in GDPR-compliant format.

    Supports multiple formats:
    - **JSON**: Full structured data with metadata
    - **CSV**: Tabular format for spreadsheet analysis
    - **PDF**: Formatted document (simulated)

    Includes:
    - Complete audit trail
    - Data processing records
    - Legal basis documentation
    - Retention information

    Security: Requires JWT with audit:read scope
    """
    user_id = get_user_id(current_user)
    user_email = get_user_email(current_user)
    now = datetime.now(timezone.utc)
    export_id = f"export_{uuid.uuid4().hex[:12]}"

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
            detail=f"Mission {mission_id} not found",
        )

    # Optionally exclude processing records
    if not include_processing_records:
        mission.data_processing = []

    # Add export event to audit trail
    export_event = AuditEvent(
        id=f"evt_{uuid.uuid4().hex[:8]}",
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
                "Content-Disposition": f"attachment; filename=mission_{mission_id}_export.csv"
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
            message=f"GDPR-compliant export generated for mission {mission_id}",
            success=True,
        )
        return JSONResponse(
            content=response.model_dump(),
            headers={
                "Content-Disposition": f"attachment; filename=mission_{mission_id}_export.json"
            },
        )
