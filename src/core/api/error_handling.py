#!/usr/bin/env python3
"""
Enhanced Error Handling and Diagnostics System
Provides detailed error diagnostics, troubleshooting hints, and consistent error responses
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ErrorDiagnostics:
    """Enhanced error diagnostics with troubleshooting hints"""

    @staticmethod
    def analyze_error(
        error: Exception, context: str = ""
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze an error and provide detailed diagnostics

        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred

        Returns: dict[str, Any]ionary with error analysis and troubleshooting information  # TODO(TYPE): replace Any with concrete type
        """
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Module/Import errors
        if "import" in error_str or "module" in error_str or "attribute" in error_str:
            return {
                "category": "dependency_error",
                "status_code": 503,
                "error": "Service dependency error",
                "message": f"Module or dependency issue: {str(error)[:200]}",
                "troubleshooting": [
                    "Check if all required dependencies are installed",
                    "Verify system initialization completed successfully",
                    "Check for missing modules or circular imports",
                    "Restart the service if dependencies were recently updated",
                ],
                "error_type": error_type,
            }

        # Database/Connection errors
        elif any(term in error_str for term in ["connection", "timeout", "database", "pool"]):
            return {
                "category": "connectivity_error",
                "status_code": 503,
                "error": "Service connectivity issue",
                "message": f"Connection or database issue: {str(error)[:200]}",
                "troubleshooting": [
                    "Check database connection and availability",
                    "Verify network connectivity",
                    "Check if connection pool is exhausted",
                    "Verify service endpoints are accessible",
                ],
                "error_type": error_type,
            }

        # Permission/Access errors
        elif any(
            term in error_str for term in ["permission", "access", "forbidden", "unauthorized"]
        ):
            return {
                "category": "access_error",
                "status_code": 403,
                "error": "Access permission error",
                "message": f"Permission or access issue: {str(error)[:200]}",
                "troubleshooting": [
                    "Check file and directory permissions",
                    "Verify authentication credentials",
                    "Check if user has required access rights",
                    "Verify API keys and tokens are valid",
                ],
                "error_type": error_type,
            }

        # Validation/Input errors
        elif any(term in error_str for term in ["invalid", "validation", "format", "parse"]):
            return {
                "category": "validation_error",
                "status_code": 400,
                "error": "Input validation error",
                "message": f"Invalid input or format: {str(error)[:200]}",
                "troubleshooting": [
                    "Check input data format and required fields",
                    "Verify parameter types and values",
                    "Check for missing or malformed data",
                    "Review API documentation for correct format",
                ],
                "error_type": error_type,
            }

        # Resource/Memory errors
        elif any(term in error_str for term in ["memory", "resource", "limit", "quota"]):
            return {
                "category": "resource_error",
                "status_code": 507,
                "error": "Resource exhaustion error",
                "message": f"Resource limit or memory issue: {str(error)[:200]}",
                "troubleshooting": [
                    "Check system memory and disk space",
                    "Monitor resource usage and limits",
                    "Consider increasing allocated resources",
                    "Check for memory leaks or resource cleanup",
                ],
                "error_type": error_type,
            }

        # Configuration errors
        elif any(term in error_str for term in ["config", "setting", "environment", "variable"]):
            return {
                "category": "configuration_error",
                "status_code": 500,
                "error": "Configuration error",
                "message": f"Configuration or environment issue: {str(error)[:200]}",
                "troubleshooting": [
                    "Check configuration files and environment variables",
                    "Verify all required settings are present",
                    "Check for configuration file syntax errors",
                    "Ensure environment is properly initialized",
                ],
                "error_type": error_type,
            }

        # Generic server errors
        else:
            return {
                "category": "server_error",
                "status_code": 500,
                "error": "Internal server error",
                "message": f"Unexpected error occurred: {str(error)[:200]}",
                "troubleshooting": [
                    "Check server logs for detailed error information",
                    "Verify system health and status",
                    "Try the request again after a brief wait",
                    "Contact system administrator if problem persists",
                ],
                "error_type": error_type,
            }

    @staticmethod
    def create_http_exception(error: Exception, context: str = "") -> HTTPException:
        """
        Create a detailed HTTPException with diagnostics

        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred

        Returns:
            HTTPException with detailed error information
        """
        analysis = ErrorDiagnostics.analyze_error(error, context)

        detail = {
            "error": analysis["error"],
            "message": analysis["message"],
            "troubleshooting": analysis["troubleshooting"],
            "error_type": analysis["error_type"],
            "category": analysis["category"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if context:
            detail["context"] = context

        logger.error(f"Error in {context}: {error}", exc_info=True)

        return HTTPException(status_code=analysis["status_code"], detail=detail)


def handle_endpoint_error(error: Exception, endpoint_name: str) -> HTTPException:
    """
    Convenience function for handling endpoint errors

    Args:
        error: The exception that occurred
        endpoint_name: Name of the endpoint where error occurred

    Returns:
        HTTPException with detailed diagnostics
    """
    return ErrorDiagnostics.create_http_exception(error, f"{endpoint_name} endpoint")


# Common error response templates
ERROR_TEMPLATES = {
    "agent_not_found": {
        "error": "Agent not found",
        "troubleshooting": [
            "Check if the agent ID is correct",
            "Verify the agent exists and is registered",
            "Check if the agent was deleted or deactivated",
        ],
    },
    "template_not_found": {
        "error": "Template not found",
        "troubleshooting": [
            "Check available templates using GET /templates",
            "Verify template ID format is correct",
            "Check if template exists for the specified archetype",
        ],
    },
    "service_unavailable": {
        "error": "Service temporarily unavailable",
        "troubleshooting": [
            "Wait a moment and try again",
            "Check if system is under maintenance",
            "Verify all required services are running",
        ],
    },
}


def get_template_error(
    template_name: str, **kwargs: Any
) -> dict[str, Any]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
    """Get a predefined error template with custom values"""
    template = ERROR_TEMPLATES.get(template_name, {})
    result = template.copy()
    result.update(kwargs)
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result
