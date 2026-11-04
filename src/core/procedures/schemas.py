"""
Pydantic schemas for Phase 3 procedures system (DomainPacks, ProcedureMetadata, Executions)
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# DOMAIN PACK SCHEMAS
# ============================================================================


class DomainPackCreate(BaseModel):
    """Schema for creating a new domain pack"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Domain pack name (e.g., 'Finance', 'Legal')",
    )
    department: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Department responsible for this pack",
    )
    version: int = Field(default=1, ge=1, description="Domain pack version")
    description: str | None = Field(None, max_length=2000, description="Detailed description")
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capability categories (e.g., 'compliance', 'risk_analysis')",
    )
    input_contracts: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Schema for expected inputs"
    )
    output_contracts: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Schema for expected outputs"
    )
    status: str | None = Field(default="active", description="Status: active, deprecated, archival")


class DomainPackUpdate(BaseModel):
    """Schema for updating a domain pack"""

    department: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=2000)
    capabilities: list[str] | None = None
    input_contracts: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    output_contracts: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    status: str | None = None


class DomainPackRead(BaseModel):
    """Schema for reading domain pack data"""

    id: UUID
    tenant_id: int
    name: str
    department: str
    version: int
    description: str | None
    capabilities: list[str]
    input_contracts: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    output_contracts: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PROCEDURE METADATA SCHEMAS
# ============================================================================


class ProcedureMetadataCreate(BaseModel):
    """Schema for creating procedure metadata"""

    flow_id: UUID = Field(..., description="Reference to FocusBuilderFlow")
    domain_pack_id: UUID = Field(..., description="Reference to DomainPack")
    category: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Procedure category (e.g., 'invoice_approval')",
    )
    description: str | None = Field(None, max_length=2000)
    intent_tags: list[str] = Field(
        default_factory=list, description="Search tags for intent matching"
    )
    prerequisites: list[str] = Field(
        default_factory=list, description="Pre-conditions for execution"
    )
    estimated_duration_minutes: int | None = Field(
        None, ge=1, description="Estimated execution time"
    )
    is_platform_template: bool = Field(
        default=False, description="Is this a platform-provided template?"
    )
    metadata_json: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Additional metadata as JSONB"
    )


class ProcedureMetadataUpdate(BaseModel):
    """Schema for updating procedure metadata"""

    description: str | None = None
    intent_tags: list[str] | None = None
    prerequisites: list[str] | None = None
    estimated_duration_minutes: int | None = None
    is_platform_template: bool | None = None
    metadata_json: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class ProcedureMetadataRead(BaseModel):
    """Schema for reading procedure metadata"""

    id: UUID
    tenant_id: UUID
    flow_id: UUID
    domain_pack_id: UUID
    category: str
    description: str | None
    intent_tags: list[str]
    prerequisites: list[str]
    estimated_duration_minutes: int | None
    is_platform_template: bool
    metadata_json: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcedureRead(BaseModel):
    """Combined view of flow + metadata"""

    id: UUID
    flow_id: UUID
    name: str
    category: str
    description: str | None
    intent_tags: list[str]
    domain_pack_id: UUID
    is_published: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PROCEDURE EXECUTION SCHEMAS
# ============================================================================


class ProcedureExecutionCreate(BaseModel):
    """Schema for creating a new procedure execution"""

    procedure_id: UUID = Field(..., description="Reference to ProcedureMetadata")
    input: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Input data for procedure execution"
    )


class ProcedureExecutionRead(BaseModel):
    """Schema for reading procedure execution"""

    id: UUID
    tenant_id: UUID
    procedure_id: UUID
    status: str
    error_message: str | None
    audit_trail: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ProcedureExecutionStatusUpdate(BaseModel):
    """Schema for updating execution status"""

    status: str = Field(
        ...,
        description="New status (pending_approval, running, completed, failed, etc.)",
    )
    output: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None


# ============================================================================
# AI QUALITY EVENT SCHEMAS
# ============================================================================


class AIQualityEventCreate(BaseModel):
    """Schema for creating AI quality event"""

    execution_id: UUID = Field(..., description="Reference to ProcedureExecution")
    event_type: str = Field(
        ...,
        description="Type: hallucination, low_confidence, policy_violation, timeout",
    )
    severity: str = Field(..., description="Severity: info, warning, error, critical")
    details: dict[str, Any] = Field(default_factory=dict, description="Event details as JSONB")  # TODO(TYPE): replace Any with concrete type


class AIQualityEventRead(BaseModel):
    """Schema for reading AI quality event"""

    id: UUID
    execution_id: UUID
    event_type: str
    severity: str
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# MULTI-PACK ASSEMBLY SCHEMAS (Sprint 3 Slice 1)
# ============================================================================


class ExecutionStep(BaseModel):
    """Individual step within a pack segment"""

    step_id: str = Field(..., description="Unique step identifier")
    action: str = Field(..., description="Action to perform")
    estimated_duration_seconds: int = Field(default=60, ge=1, description="Estimated step duration")
    requires_approval: bool = Field(default=False, description="Does this step need approval?")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional step metadata")  # TODO(TYPE): replace Any with concrete type


class PackSegment(BaseModel):
    """Segment of execution graph representing one domain pack"""

    pack_id: UUID = Field(..., description="Domain pack ID")
    domain: str = Field(..., description="Domain name (e.g., 'finance', 'legal')")
    order: int = Field(..., ge=1, description="Execution order")
    name: str = Field(..., description="Human-readable pack name")
    dependencies: list[str] = Field(
        default_factory=list, description="Domains this segment depends on"
    )
    steps: list[ExecutionStep] = Field(
        default_factory=list, description="Execution steps within this segment"
    )
    estimated_duration_minutes: int = Field(
        default=5, ge=1, description="Estimated segment duration"
    )
    requires_approval: bool = Field(default=False, description="Does this segment need approval?")


class ExecutionGraph(BaseModel):
    """Complete execution graph for cross-department workflow"""

    graph_id: UUID = Field(default_factory=UUID, description="Unique graph identifier")
    tenant_id: UUID = Field(..., description="Tenant owning this graph")
    segments: list[PackSegment] = Field(
        default_factory=list, description="Ordered list of pack segments"
    )
    estimated_duration_minutes: int = Field(default=0, ge=0, description="Total estimated duration")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Graph creation timestamp"
    )

    model_config = ConfigDict(from_attributes=True)
