"""
Request Validation Error Customization

User-friendly validation error responses.

Part of SC-8.1 implementation.
"""

from typing import Any, cast
from collections.abc import Callable, Sequence

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def format_validation_errors(errors: Sequence[Any]) -> list[dict[str, str]]:  # TODO(TYPE): replace Any with concrete type
    """
    Format Pydantic validation errors into user-friendly format.

    Args:
        errors: Raw Pydantic error list

    Returns: list[Any] of simplified error dicts with 'field' and 'error' keys  # TODO(TYPE): replace Any with concrete type
    """
    formatted: list[dict[str, str]] = []
    for error in errors:
        # Get field name from location
        loc = error.get("loc", [])
        field = ".".join(str(cast(Any, item)) for item in loc if item != "body")  # TODO(TYPE): replace Any with concrete type

        # Get message
        msg = error.get("msg", "Invalid value")
        error_type = error.get("type", "")

        # Make messages more user-friendly
        if "missing" in error_type:
            msg = "This field is required"
        elif "type_error" in error_type:
            msg = f"Invalid type: {msg}"
        elif "value_error" in error_type:
            msg = msg.replace("value_error.", "")

        formatted.append({"field": field or "request", "error": msg})

    return formatted


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Custom handler for RequestValidationError.

    Returns user-friendly error format instead of default Pydantic output.
    """
    errors = format_validation_errors(exc.errors())

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "message": "Validation failed",
            "code": "VALIDATION_ERROR",
            "errors": errors,
        },
    )


def register_validation_handlers(app: FastAPI) -> None:
    """
    Register custom validation error handlers on FastAPI app.

    Usage:
        from src.core.exceptions.validation import register_validation_handlers
        register_validation_handlers(app)
    """
    app.add_exception_handler(
        RequestValidationError,
        cast(Callable[[Any, Exception], Any], validation_exception_handler),  # TODO(TYPE): replace Any with concrete type
    )
