"""Pydantic schemas for GDPR Compliance domain (ADR-033 Laag 1)."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExportFormat(str, Enum):
    """Export data formats."""

    JSON = "json"
    CSV = "csv"


class DataCategory(str, Enum):
    """GDPR data categories."""

    PERSONAL = "personal"
    AGENTS = "agents"
    TASKS = "tasks"
    WORKFLOWS = "workflows"
    AUDIT = "audit"
    ALL = "all"


class DeleteType(str, Enum):
    """Delete operation types."""

    SOFT = "soft"
    HARD = "hard"


class ComplianceCategory(str, Enum):
    """Categories of compliance requirements."""

    DATA_COLLECTION = "data_collection"
    DATA_PROCESSING = "data_processing"
    DATA_STORAGE = "data_storage"
    DATA_TRANSFER = "data_transfer"
    CONSENT_MANAGEMENT = "consent_management"
    ACCESS_RIGHTS = "access_rights"
    DELETION_RIGHTS = "deletion_rights"
    SECURITY_MEASURES = "security_measures"
    DATA_BREACH = "data_breach"


class ComplianceStatus(str, Enum):
    """Status of compliance requirement."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXEMPT = "exempt"
    N_A = "n_a"


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------


class ExportDataRequest(BaseModel):
    """Request model for data export."""

    categories: list[DataCategory] = Field(
        default=[DataCategory.ALL], description="Data categories to export"
    )
    format: ExportFormat = Field(
        default=ExportFormat.JSON, description="Export format (JSON or CSV)"
    )
    include_metadata: bool = Field(default=True, description="Include creation/update timestamps")


class ExportDataResponse(BaseModel):
    """Response model for data export."""

    tenant_id: str
    export_date: datetime
    categories: list[DataCategory]
    total_records: int
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


# ---------------------------------------------------------------------------
# Delete schemas
# ---------------------------------------------------------------------------


class DeleteDataRequest(BaseModel):
    """Request model for data deletion."""

    delete_type: DeleteType = Field(
        default=DeleteType.SOFT,
        description="Soft delete (30-day retention) or hard delete (permanent)",
    )
    confirmation_code: str = Field(
        ..., description="Confirmation code (must match tenant_id for safety)"
    )
    reason: str | None = Field(None, max_length=500, description="Reason for deletion (optional)")

    @field_validator("confirmation_code")
    @classmethod
    def validate_confirmation(cls, v: str) -> str:
        """Ensure confirmation code is provided."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Confirmation code is required")
        return v


class DeleteDataResponse(BaseModel):
    """Response model for data deletion."""

    tenant_id: str
    delete_type: DeleteType
    deletion_date: datetime
    scheduled_purge_date: datetime | None
    records_deleted: int
    categories_deleted: list[str]
    message: str = ""


class TenantExportRequest(BaseModel):
    """Aanvraag van de tenantbrede export die aan een wissing voorafgaat."""

    recipient: Literal["klant", "bewaarder", "curator"] = Field(
        default="klant",
        description="Voor wie de export is: de klant, de bewaarder (BW 2:24) of de curator (Fw 105b)",
    )
    recipient_name: str | None = Field(None, max_length=200, description="Naam van de ontvanger")


class TenantExportResponse(BaseModel):
    """De export van alle tenantgegevens, met controlegetal en uitleg."""

    recipient: str
    sha256: str
    tables: int
    rows: int
    truncated_tables: list[str]
    message: str
    data: dict[str, dict[str, object]]


class EraseUserResponse(BaseModel):
    """Antwoord op het aanvragen van de wissing van een medewerker (AVG art. 17, na 30 dagen)."""

    user_id: int
    status: str
    scheduled_purge_date: datetime
    message: str


class RevokeResponse(BaseModel):
    """Antwoord op het intrekken van een wissingsaanvraag."""

    status: str
    users_reactivated: int


# ---------------------------------------------------------------------------
# Audit trail schemas
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: str
    timestamp: datetime
    action: str
    resource: str | None = None
    user_id: str
    client_ip: str | None = None
    details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class AuditTrailRequest(BaseModel):
    """Request model for audit trail."""

    start_date: datetime | None = Field(None, description="Filter logs from this date")
    end_date: datetime | None = Field(None, description="Filter logs until this date")
    action_type: str | None = Field(
        None, description="Filter by action type (create, read, update, delete)"
    )
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=100, ge=1, le=1000, description="Items per page")


class AuditTrailResponse(BaseModel):
    """Response model for audit trail."""

    tenant_id: str
    total_logs: int
    page: int
    page_size: int
    total_pages: int
    logs: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# Compliance checklist schemas
# ---------------------------------------------------------------------------


class ComplianceRequirement(BaseModel):
    """A single compliance requirement."""

    id: str = Field(..., description="Unique requirement ID")
    category: ComplianceCategory = Field(..., description="Requirement category")
    title: str = Field(..., description="Requirement title")
    description: str = Field(..., description="Detailed requirement description")
    regulation: str = Field(..., description="Applicable regulation (e.g., GDPR Article 5)")
    mandatory: bool = Field(True, description="Whether this requirement is mandatory")
    status: ComplianceStatus = Field(ComplianceStatus.NOT_STARTED, description="Current status")
    evidence: str | None = Field(default=None, description="Evidence of compliance")
    due_date: str | None = Field(default=None, description="Compliance due date")
    notes: str | None = Field(default=None, description="Additional notes")
    last_updated: str | None = Field(default=None, description="Last updated timestamp")


class ComplianceChecklist(BaseModel):
    """Complete GDPR compliance checklist."""

    tenant_id: str = Field(..., description="Tenant ID")
    checklist_id: str = Field(..., description="Checklist instance ID")
    requirements: list[ComplianceRequirement] = Field(
        default_factory=list, description="Compliance requirements"
    )
    overall_status: ComplianceStatus = Field(..., description="Overall compliance status")
    last_assessment: str = Field(..., description="Last assessment timestamp")
    next_review: str | None = Field(None, description="Next review date")
    score: float = Field(..., ge=0, le=100, description="Compliance score percentage")


class ComplianceChecklistResponse(BaseModel):
    """Response for compliance checklist endpoint."""

    checklist: ComplianceChecklist
    message: str
    completed_requirements: int
    total_requirements: int
