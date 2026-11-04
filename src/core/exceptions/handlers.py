"""
Exception Handlers for Sanskriti Setu AI Platform
Handles custom exceptions and converts them to standardized error responses.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, NoReturn

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.exceptions.exceptions import (
    NotFoundError,
    RBACError,
    SanskritiError,
    TenantError,
    ValidationError,
    WorkflowError,
)

# Configure logger
logger = logging.getLogger(__name__)


async def sanskriti_error_handler(request: Request, exc: SanskritiError) -> JSONResponse:
    """
    Handle SanskritiError and subclasses.

    Converts custom exceptions to standardized JSON error responses.
    """
    # Log the error with context
    logger.error(
        "SanskritiError: %s - %s",
        exc.error_code,
        exc.message,
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": request.url.path,
            "method": request.method,
        },
    )

    # Return standardized error response
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException.

    Converts HTTP exceptions to standardized JSON error responses.
    """
    # Log the error with context
    logger.warning(
        "HTTPException: %s - %s",
        exc.status_code,
        exc.detail,
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
            "method": request.method,
        },
    )

    # Convert to standardized error format
    error_details: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "status_code": exc.status_code
    }  # TODO(TYPE): replace Any with concrete type
    error_response: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "error": {
            "error_code": "HTTP_ERROR",
            "message": exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "details": error_details,
        },
        "detail": exc.detail,
    }

    # Add headers if present
    if hasattr(exc, "headers") and exc.headers:
        error_details["headers"] = exc.headers

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
        headers=exc.headers if hasattr(exc, "headers") else None,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unhandled exceptions.

    Converts unexpected exceptions to standardized JSON error responses.
    """
    # Log the full traceback for debugging - MUST be in message for Docker logs visibility
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception on %s %s: %s: %s\n%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        str(exc),
        tb,
    )

    # Don't expose internal details in production
    error_response = {
        "error": {
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "details": {},
        }
    }

    return JSONResponse(status_code=500, content=error_response)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    # Register handlers for custom exceptions
    app.add_exception_handler(SanskritiError, sanskriti_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(WorkflowError, sanskriti_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TenantError, sanskriti_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RBACError, sanskriti_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, sanskriti_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NotFoundError, sanskriti_error_handler)  # type: ignore[arg-type]

    # Register handler for HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]

    # Register catch-all handler for unexpected exceptions
    app.add_exception_handler(Exception, general_exception_handler)


# Convenience functions for raising common exceptions


def raise_not_found(resource_type: str, resource_id: str | None = None) -> NoReturn:
    """Raise a standardized NotFoundError."""
    from src.core.exceptions.exceptions import NotFoundError

    raise NotFoundError(resource_type, resource_id)


def raise_validation_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Raise a standardized ValidationError."""
    from src.core.exceptions.exceptions import ValidationError

    raise ValidationError(message, details=details)


def raise_permission_denied(permission: str, resource: str, user_id: str) -> NoReturn:
    """Raise a standardized PermissionDeniedError."""
    from src.core.exceptions.exceptions import PermissionDeniedError

    raise PermissionDeniedError(permission, resource, user_id)


def raise_tenant_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Raise a standardized TenantError."""
    from src.core.exceptions.exceptions import TenantError

    raise TenantError(message, details=details)


def raise_workflow_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Raise a standardized WorkflowError."""
    from src.core.exceptions.exceptions import WorkflowError

    raise WorkflowError(message, details=details)
