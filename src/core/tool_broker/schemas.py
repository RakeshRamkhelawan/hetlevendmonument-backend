# core/tool_broker/schemas.py
"""
Enhanced Pydantic schemas for Tool Broker with comprehensive validation
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ToolCategory(str, Enum):
    """Supported tool categories"""

    SERENA = "serena"
    SEQUENTIAL_THINKING = "sequential_thinking"


class ToolExecutionRequest(BaseModel):
    """Enhanced request for tool execution with validation."""

    tool_name: ToolCategory = Field(
        ..., description="Tool category: 'serena' or 'sequential_thinking'"
    )
    sub_tool: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Specific tool/function name, e.g. 'find_symbol'",
    )
    params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Tool parameters as dictionary"
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=300,
        description="Optional timeout override in seconds (1-300)",
    )
    request_id: str | None = Field(
        default=None, max_length=100, description="Optional request ID for tracing"
    )

    @field_validator("sub_tool")
    @classmethod
    def validate_sub_tool(cls, v: str) -> str:
        """Validate sub_tool name format"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"Sub-tool name must contain only alphanumeric characters, hyphens, and underscores: {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_request(self) -> "ToolExecutionRequest":
        """Root-level request validation"""
        params = self.params

        # Ensure params is a dict
        if params is not None and not isinstance(params, dict):
            raise ValueError("Params must be a dictionary")

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tool_name": "serena",
                "sub_tool": "find_symbol",
                "params": {"name": "my_function", "file": "main.py"},
                "timeout_seconds": 30,
                "request_id": "req_12345",
            }
        }
    )


class ToolExecutionResponse(BaseModel):
    """Enhanced response for tool execution."""

    success: bool = Field(..., description="Whether execution succeeded")
    result: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Tool execution result (on success)"
    )
    error_message: str | None = Field(default=None, description="Error message (on failure)")
    execution_time_ms: float | None = Field(
        default=None, ge=0, description="Tool execution time in milliseconds"
    )
    request_id: str | None = Field(default=None, description="Request ID for tracing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "result": {"symbols": ["func1", "func2"]},
                "error_message": None,
                "execution_time_ms": 45.2,
                "request_id": "req_12345",
            }
        }
    )


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: bool = Field(default=True, description="Always True for error responses")
    status_code: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Error timestamp")
    request_id: str | None = Field(default=None, description="Request ID for tracing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": True,
                "status_code": 400,
                "message": "Invalid tool name",
                "detail": "Tool 'invalid_tool' not found in registry",
                "timestamp": "2025-10-18T10:30:00Z",
                "request_id": "req_12345",
            }
        }
    )


class TokenRequest(BaseModel):
    """Request to obtain a JWT token."""

    username: str = Field(
        ..., min_length=1, max_length=100, description="Username for authentication"
    )
    password: str = Field(
        ..., min_length=8, max_length=256, description="Password (minimum 8 characters)"
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"username": "admin", "password": "secure_password_123"}}
    )


class TokenResponse(BaseModel):
    """Response containing JWT token."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., ge=1, description="Token expiration time in seconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Check timestamp")
    service_name: str = Field(default="Tool Broker Service", description="Name of the service")
    version: str = Field(default="2.0.0", description="Service version")
    components: dict[str, str] = Field(
        default_factory=dict, description="Status of individual components"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": "2025-10-18T10:30:00Z",
                "service_name": "Tool Broker Service",
                "version": "2.0.0",
                "components": {
                    "serena_client": "operational",
                    "sequential_thinking_client": "operational",
                    "database": "operational",
                },
            }
        }
    )


class ToolHITLRequest(BaseModel):
    """Request to create a HITL approval ticket for a HIGH-risk tool."""

    agent_id: str = Field(
        ..., min_length=1, max_length=100, description="Agent requesting the tool"
    )
    tool_name: str = Field(
        ..., min_length=1, max_length=200, description="Tool name to be executed"
    )
    tool_input: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")  # TODO(TYPE): replace Any with concrete type
    reason: str = Field(
        ..., min_length=10, max_length=500, description="Business justification for tool use"
    )
    task_id: str | None = Field(None, max_length=100, description="Optional task ID for tracing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "agent-finance-01",
                "tool_name": "local__send_email",
                "tool_input": {"to": "ops@tenant1.com", "subject": "Cleanup report #4412"},
                "reason": "Sending the scheduled cleanup report to the operations mailbox #4412",
                "task_id": "task-4412",
            }
        }
    )


class ToolHITLApproval(BaseModel):
    """Approve a pending HITL ticket. approved_by is set server-side from current_user.email."""

    ticket_ref: str = Field(
        ..., min_length=1, max_length=50, description="Ticket reference to approve"
    )
    notes: str | None = Field(None, max_length=1000, description="Optional reviewer notes")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ticket_ref": "TOOL-A1B2C3D4",
                "notes": "Confirmed with team lead; temp dir is safe to remove.",
            }
        }
    )


class ToolHITLRejection(BaseModel):
    """Reject a pending HITL ticket. rejected_by is set server-side from current_user.email."""

    ticket_ref: str = Field(
        ..., min_length=1, max_length=50, description="Ticket reference to reject"
    )
    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for rejection")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ticket_ref": "TOOL-A1B2C3D4",
                "reason": "Command targets a production directory, not a temp dir. Use cleanup script instead.",
            }
        }
    )
