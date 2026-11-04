# core/tool_broker/exceptions.py
"""
Enhanced Exception Hierarchy for Tool Broker
Includes error codes, context enrichment, and MCP-specific errors
"""

import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

from fastapi import HTTPException, status


class ToolBrokerErrorCode(str, Enum):
    """Standardized error codes for Tool Broker exceptions"""

    # General errors (1xxx)
    UNKNOWN_ERROR = "TB_1000"
    INTERNAL_ERROR = "TB_1001"
    CONFIGURATION_ERROR = "TB_1002"

    # Tool errors (2xxx)
    TOOL_NOT_FOUND = "TB_2000"
    TOOL_INVALID = "TB_2001"
    TOOL_EXECUTION_FAILED = "TB_2002"
    TOOL_TIMEOUT = "TB_2003"
    TOOL_VALIDATION_FAILED = "TB_2004"

    # MCP errors (3xxx)
    MCP_CONNECTION_FAILED = "TB_3000"
    MCP_INITIALIZATION_FAILED = "TB_3001"
    MCP_SUBPROCESS_FAILED = "TB_3002"
    MCP_PROTOCOL_ERROR = "TB_3003"
    MCP_TOOL_NOT_AVAILABLE = "TB_3004"
    MCP_SESSION_EXPIRED = "TB_3005"
    MCP_RESPONSE_INVALID = "TB_3006"

    # External service errors (4xxx)
    SERVICE_UNAVAILABLE = "TB_4000"
    SERVICE_TIMEOUT = "TB_4001"
    SERVICE_API_ERROR = "TB_4002"
    SERVICE_AUTHENTICATION_FAILED = "TB_4003"

    # Security errors (5xxx)
    AUTHENTICATION_FAILED = "TB_5000"
    AUTHORIZATION_FAILED = "TB_5001"
    TOKEN_INVALID = "TB_5002"
    TOKEN_EXPIRED = "TB_5003"
    PERMISSION_DENIED = "TB_5004"
    RATE_LIMIT_EXCEEDED = "TB_5005"

    # Validation errors (6xxx)
    VALIDATION_FAILED = "TB_6000"
    INVALID_REQUEST = "TB_6001"
    INVALID_RESPONSE = "TB_6002"
    SCHEMA_MISMATCH = "TB_6003"


class ToolBrokerException(HTTPException):
    """
    Enhanced base exception for Tool Broker related errors

    Includes:
    - Error codes for categorization
    - Context enrichment for debugging
    - Timestamp tracking
    - Original error preservation
    """

    def __init__(
        self,
        status_code: int,
        detail: Any,  # TODO(TYPE): replace Any with concrete type
        error_code: ToolBrokerErrorCode = ToolBrokerErrorCode.UNKNOWN_ERROR,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        original_error: Exception | None = None,
    ) -> None:
        # Enrich detail with error code
        enriched_detail: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        if isinstance(detail, str):
            enriched_detail = {
                "message": detail,
                "error_code": error_code.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Add context if provided
            if context:
                enriched_detail["context"] = cast(Any, context)  # TODO(TYPE): replace Any with concrete type

            # Add original error details if available
            if original_error:
                enriched_detail["original_error"] = cast(
                    Any,  # TODO(TYPE): replace Any with concrete type
                    {
                        "type": type(original_error).__name__,
                        "message": str(original_error),
                    },
                )

                # Add traceback in development (can be controlled by config)
                if self._should_include_traceback():
                    enriched_detail["traceback"] = traceback.format_exc()
        else:
            enriched_detail = cast(dict[str, Any], detail)  # TODO(TYPE): replace Any with concrete type

        super().__init__(status_code=status_code, detail=enriched_detail)

        # Store additional attributes
        self.error_code = error_code
        self.context = context or {}
        self.original_error = original_error
        self.timestamp = datetime.now(timezone.utc)

    @staticmethod
    def _should_include_traceback() -> bool:
        """Determine if traceback should be included (based on environment)"""
        # TODO: Check environment variable or config
        # For now, always include for better debugging
        return True

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert exception to dictionary for logging/monitoring"""
        return {
            "error_code": self.error_code.value,
            "status_code": self.status_code,
            "message": str(self.detail),
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "original_error": str(self.original_error) if self.original_error else None,
        }


class ToolExecutionException(ToolBrokerException):
    """Exception raised when a tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        error_detail: str,
        original_error: Exception | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context["tool_name"] = tool_name

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tool execution failed: {error_detail}",
            error_code=ToolBrokerErrorCode.TOOL_EXECUTION_FAILED,
            context=enriched_context,
            original_error=original_error,
        )
        self.tool_name = tool_name


class ExternalServiceConnectionError(ToolBrokerException):
    """Exception raised for connection errors to external services."""

    def __init__(
        self,
        service_name: str,
        original_error: Exception,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context["service_name"] = service_name

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to {service_name} service. Please check service availability.",
            error_code=ToolBrokerErrorCode.SERVICE_UNAVAILABLE,
            context=enriched_context,
            original_error=original_error,
        )
        self.service_name = service_name


class ExternalServiceAPIError(ToolBrokerException):
    """Exception raised for API errors from external services."""

    def __init__(
        self,
        service_name: str,
        status_code: int,
        response_detail: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update(
            {
                "service_name": service_name,
                "service_status_code": status_code,
                "service_response": response_detail,
            }
        )

        super().__init__(
            status_code=status_code,
            detail=f"{service_name} API returned an error ({status_code}): {response_detail}",
            error_code=ToolBrokerErrorCode.SERVICE_API_ERROR,
            context=enriched_context,
        )
        self.service_name = service_name
        self.response_detail = response_detail


# ============================================================================
# MCP-Specific Exceptions (NEW)
# ============================================================================


class MCPConnectionError(ToolBrokerException):
    """Exception raised when MCP server connection fails."""

    def __init__(
        self,
        server_name: str,
        original_error: Exception,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context["mcp_server"] = server_name

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to MCP server '{server_name}'",
            error_code=ToolBrokerErrorCode.MCP_CONNECTION_FAILED,
            context=enriched_context,
            original_error=original_error,
        )
        self.server_name = server_name


class MCPInitializationError(ToolBrokerException):
    """Exception raised when MCP session initialization fails."""

    def __init__(
        self,
        server_name: str,
        original_error: Exception,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context["mcp_server"] = server_name

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize MCP session for server '{server_name}'",
            error_code=ToolBrokerErrorCode.MCP_INITIALIZATION_FAILED,
            context=enriched_context,
            original_error=original_error,
        )
        self.server_name = server_name


class MCPSubprocessError(ToolBrokerException):
    """Exception raised when MCP subprocess fails to start or crashes."""

    def __init__(
        self,
        server_name: str,
        command: str,
        original_error: Exception,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update({"mcp_server": server_name, "command": command})

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP subprocess failed for server '{server_name}'",
            error_code=ToolBrokerErrorCode.MCP_SUBPROCESS_FAILED,
            context=enriched_context,
            original_error=original_error,
        )
        self.server_name = server_name
        self.command = command


class MCPProtocolError(ToolBrokerException):
    """Exception raised when MCP protocol communication fails."""

    def __init__(
        self,
        server_name: str,
        protocol_error: str,
        original_error: Exception | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update({"mcp_server": server_name, "protocol_error": protocol_error})

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP protocol error for server '{server_name}': {protocol_error}",
            error_code=ToolBrokerErrorCode.MCP_PROTOCOL_ERROR,
            context=enriched_context,
            original_error=original_error,
        )
        self.server_name = server_name
        self.protocol_error = protocol_error


class MCPToolNotAvailableError(ToolBrokerException):
    """Exception raised when requested MCP tool is not available."""

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        available_tools: list[str] | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update({"mcp_server": server_name, "requested_tool": tool_name})

        if available_tools:
            enriched_context["available_tools"] = available_tools

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not available on MCP server '{server_name}'",
            error_code=ToolBrokerErrorCode.MCP_TOOL_NOT_AVAILABLE,
            context=enriched_context,
        )
        self.server_name = server_name
        self.tool_name = tool_name
        self.available_tools = available_tools


class MCPResponseInvalidError(ToolBrokerException):
    """Exception raised when MCP response is invalid or malformed."""

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        reason: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update(
            {"mcp_server": server_name, "tool_name": tool_name, "reason": reason}
        )

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid response from MCP server '{server_name}' for tool '{tool_name}': {reason}",
            error_code=ToolBrokerErrorCode.MCP_RESPONSE_INVALID,
            context=enriched_context,
        )
        self.server_name = server_name
        self.tool_name = tool_name
        self.reason = reason


# ============================================================================
# Updated Existing Exceptions
# ============================================================================


class ToolNotFoundException(ToolBrokerException):
    """Exception raised when a requested tool is not found."""

    def __init__(self, tool_name: str, context: dict[str, Any] | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        enriched_context = context or {}
        enriched_context["tool_name"] = tool_name

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found in Tool Broker registry",
            error_code=ToolBrokerErrorCode.TOOL_NOT_FOUND,
            context=enriched_context,
        )
        self.tool_name = tool_name


class InvalidToolError(ToolBrokerException):
    """Exception raised when tool name is invalid."""

    def __init__(
        self,
        tool_name: str,
        reason: str = "Invalid tool name format",
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update({"tool_name": tool_name, "reason": reason})

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{reason}: {tool_name}",
            error_code=ToolBrokerErrorCode.TOOL_INVALID,
            context=enriched_context,
        )
        self.tool_name = tool_name
        self.reason = reason


class ServiceTimeoutError(ToolBrokerException):
    """Exception raised when external service times out."""

    def __init__(
        self,
        service_name: str,
        timeout_seconds: int,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context.update({"service_name": service_name, "timeout_seconds": timeout_seconds})

        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"{service_name} service did not respond within {timeout_seconds} seconds",
            error_code=ToolBrokerErrorCode.SERVICE_TIMEOUT,
            context=enriched_context,
        )
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds


class ValidationException(ToolBrokerException):
    """Exception raised for request/response validation failures."""

    def __init__(
        self,
        detail: str,
        field: str | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        error_msg = detail
        enriched_context = context or {}

        if field:
            error_msg = f"Validation error in field '{field}': {detail}"
            enriched_context["field"] = field

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
            error_code=ToolBrokerErrorCode.VALIDATION_FAILED,
            context=enriched_context,
        )
        self.field = field


class SecurityException(ToolBrokerException):
    """Base exception for security-related errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_403_FORBIDDEN,
        error_code: ToolBrokerErrorCode = ToolBrokerErrorCode.AUTHORIZATION_FAILED,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=detail,
            error_code=error_code,
            context=context,
        )


class InvalidTokenError(SecurityException):
    """Exception raised when JWT token is invalid or expired."""

    def __init__(
        self,
        reason: str = "Invalid or expired token",
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            detail=reason,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=ToolBrokerErrorCode.TOKEN_INVALID,
            context=context,
        )
        self.reason = reason


class UnauthorizedError(SecurityException):
    """Exception raised when user lacks required permissions."""

    def __init__(self, required_scope: str, context: dict[str, Any] | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        enriched_context = context or {}
        enriched_context["required_scope"] = required_scope

        super().__init__(
            detail=f"Missing required scope: {required_scope}",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=ToolBrokerErrorCode.PERMISSION_DENIED,
            context=enriched_context,
        )
        self.required_scope = required_scope


class AuthenticationError(SecurityException):
    """Exception raised when authentication fails."""

    def __init__(
        self,
        detail: str = "Authentication failed",
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=ToolBrokerErrorCode.AUTHENTICATION_FAILED,
            context=context,
        )


class RateLimitExceededError(ToolBrokerException):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self, retry_after_seconds: int = 60, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        enriched_context = context or {}
        enriched_context["retry_after_seconds"] = retry_after_seconds

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please retry after {retry_after_seconds} seconds",
            error_code=ToolBrokerErrorCode.RATE_LIMIT_EXCEEDED,
            context=enriched_context,
        )
        self.retry_after_seconds = retry_after_seconds
