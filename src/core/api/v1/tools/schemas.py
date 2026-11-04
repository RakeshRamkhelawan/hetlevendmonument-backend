"""
Pydantic schemas for Tool CRUD operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolType(str, Enum):
    """Tool execution type."""

    NATIVE = "native"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    API = "api"
    MCP = "mcp"
    WEBHOOK = "webhook"


class ToolStatus(str, Enum):
    """Tool availability status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    BETA = "beta"


class ToolParameter(BaseModel):
    """Tool parameter definition."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Parameter type (string, number, boolean, etc.)")
    description: str = Field(..., description="Parameter description")
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Any | None = Field(None, description="Default value")  # TODO(TYPE): replace Any with concrete type
    enum: list[Any] | None = Field(None, description="Allowed values")  # TODO(TYPE): replace Any with concrete type


class ToolBase(BaseModel):
    """Base Tool schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Tool name")
    description: str = Field(..., description="Tool description")
    tool_type: ToolType = Field(..., description="Tool execution type")


class ToolCreate(ToolBase):
    """Schema for creating a new tool."""

    code: str | None = Field(None, description="Tool implementation code")
    endpoint_url: str | None = Field(None, description="API endpoint URL")
    parameters: list[ToolParameter] = Field(
        default_factory=list, description="Parameter definitions"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")  # TODO(TYPE): replace Any with concrete type
    tags: list[str] = Field(default_factory=list, description="Tool tags")
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Execution timeout")
    retry_policy: dict[str, Any] = Field(default_factory=dict, description="Retry configuration")  # TODO(TYPE): replace Any with concrete type


class ToolUpdate(BaseModel):
    """Schema for updating an existing tool."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    code: str | None = None
    endpoint_url: str | None = None
    parameters: list[ToolParameter] | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    tags: list[str] | None = None
    status: ToolStatus | None = None
    timeout_seconds: int | None = Field(None, ge=1, le=300)
    retry_policy: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class ToolResponse(ToolBase):
    """Schema for tool response."""

    id: int
    tenant_id: int
    status: ToolStatus
    code: str | None = None
    endpoint_url: str | None = None
    parameters: list[ToolParameter] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int
    retry_policy: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime | None = None
    version: int = Field(default=1, description="Tool version")
    usage_count: int = Field(default=0, description="Number of times tool was used")

    class Config:
        from_attributes = True


class ToolListResponse(BaseModel):
    """Schema for list of tools with pagination."""

    data: list[ToolResponse]
    total: int
    page: int
    per_page: int


class ToolExecutionRequest(BaseModel):
    """Schema for tool execution request."""

    parameters: dict[str, Any] = Field(default_factory=dict, description="Execution parameters")  # TODO(TYPE): replace Any with concrete type
    context: dict[str, Any] = Field(default_factory=dict, description="Execution context")  # TODO(TYPE): replace Any with concrete type
    timeout_override: int | None = Field(None, ge=1, le=300)


class ToolExecutionResponse(BaseModel):
    """Schema for tool execution response."""

    success: bool
    result: Any | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    execution_time_ms: int
    logs: list[str] = Field(default_factory=list)


class ToolVersionResponse(BaseModel):
    """Schema for a single historical tool version snapshot."""

    id: int
    tool_id: int
    version: int
    snapshot: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime


class ToolVersionListResponse(BaseModel):
    """Schema for paginated tool version history."""

    data: list[ToolVersionResponse]
    total: int
    page: int
    per_page: int
