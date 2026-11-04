"""
Pydantic schemas for Procedure CRUD operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProcedureStatus(str, Enum):
    """Procedure execution status."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ProcedureStepType(str, Enum):
    """Type of procedure step."""

    TASK = "task"
    DECISION = "decision"
    PARALLEL = "parallel"
    SEQUENCE = "sequence"
    LOOP = "loop"
    WAIT = "wait"
    NOTIFY = "notify"
    API_CALL = "api_call"
    AGENT_EXECUTION = "agent_execution"


class ProcedureStep(BaseModel):
    """Individual step in a procedure."""

    id: str = Field(..., description="Step identifier")
    name: str = Field(..., description="Step name")
    description: str | None = Field(None, description="Step description")
    step_type: ProcedureStepType = Field(..., description="Type of step")
    config: dict[str, Any] = Field(default_factory=dict, description="Step configuration")  # TODO(TYPE): replace Any with concrete type
    next_steps: list[str] = Field(default_factory=list, description="IDs of next steps")
    condition: str | None = Field(
        None, description="Condition for execution (for decision steps)"
    )
    timeout_seconds: int | None = Field(None, ge=1, description="Step timeout")
    retry_count: int = Field(default=0, ge=0, description="Number of retries allowed")
    required_roles: list[str] = Field(
        default_factory=list, description="Required roles for this step"
    )


class ProcedureBase(BaseModel):
    """Base Procedure schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Procedure name")
    description: str | None = Field(None, description="Procedure description")
    department: str | None = Field(None, description="Department/division")


class ProcedureCreate(ProcedureBase):
    """Schema for creating a new procedure."""

    steps: list[ProcedureStep] = Field(..., min_length=1, description="Procedure steps")
    initial_context: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Initial context variables"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")  # TODO(TYPE): replace Any with concrete type
    tags: list[str] = Field(default_factory=list, description="Procedure tags")
    estimated_duration_minutes: int | None = Field(None, ge=1, description="Estimated duration")
    auto_execute: bool = Field(default=False, description="Auto-execute when triggered")
    trigger_conditions: list[dict[str, Any]] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list, description="Auto-trigger conditions"
    )


class ProcedureUpdate(BaseModel):
    """Schema for updating an existing procedure."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    steps: list[ProcedureStep] | None = None
    initial_context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    tags: list[str] | None = None
    status: ProcedureStatus | None = None
    estimated_duration_minutes: int | None = Field(None, ge=1)
    auto_execute: bool | None = None
    trigger_conditions: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type


class ProcedureVersion(BaseModel):
    """Procedure version information."""

    version: int
    created_at: datetime
    created_by: int
    change_summary: str | None = None


class ProcedureResponse(ProcedureBase):
    """Schema for procedure response."""

    id: int
    tenant_id: int
    version: int
    status: ProcedureStatus
    steps: list[ProcedureStep]
    initial_context: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    tags: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int | None = None
    auto_execute: bool
    trigger_conditions: list[dict[str, Any]] = Field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    created_by: int
    created_at: datetime
    updated_at: datetime | None = None
    execution_count: int = Field(default=0, description="Number of times executed")

    class Config:
        from_attributes = True


class ProcedureListResponse(BaseModel):
    """Schema for list of procedures with pagination."""

    data: list[ProcedureResponse]
    total: int
    page: int
    per_page: int


class ProcedureExecutionRequest(BaseModel):
    """Schema for procedure execution request."""

    context: dict[str, Any] = Field(default_factory=dict, description="Execution context")  # TODO(TYPE): replace Any with concrete type
    triggered_by: str | None = Field(None, description="Entity that triggered execution")
    priority: int = Field(default=5, ge=1, le=10, description="Execution priority")
    timeout_minutes: int | None = Field(None, ge=1, le=1440, description="Execution timeout")


class ProcedureExecutionResponse(BaseModel):
    """Schema for procedure execution response."""

    execution_id: str
    procedure_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    results: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    logs: list[str] = Field(default_factory=list)
