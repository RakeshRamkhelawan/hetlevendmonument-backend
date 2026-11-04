"""
Audit domain schemas -- Pydantic models and enums.

Migrated from src/core/api/audit_endpoints.py (SP-API-003 Dag 5).
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class AuditEvent(BaseModel):
    """Individual audit event in the trail"""

    id: str = Field(..., description="Event ID")
    event_type: AuditEventType = Field(..., description="Type of audit event")
    timestamp: str = Field(..., description="Event timestamp ISO format")
    actor_id: str = Field(..., description="User who performed action")
    actor_email: str | None = Field(None, description="Actor email")
    details: dict[str, Any] = Field(default_factory=dict, description="Event details")
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
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
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
