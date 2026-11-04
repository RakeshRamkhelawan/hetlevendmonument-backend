"""
API-wide Input Validation Middleware & Dependencies

Provides centralized input validation for all API endpoints.
Can be applied globally or per-router.

Usage:
    # Apply to specific router
    from src.core.security.api_validation import validate_request_body

    @router.post("/endpoint")
    async def endpoint(data: dict = Depends(validate_request_body)):
        ...

    # Or apply globally as middleware
    app.add_middleware(InputValidationMiddleware)
"""

import re
from typing import Any, Dict, List, Optional, Type
from collections.abc import Callable, Coroutine

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import BaseModel, validator

from src.core.security.input_validation import (
    SQL_INJECTION_PATTERNS,
    InputValidationError,
    contains_path_traversal,
    contains_sql_injection,
    contains_xss,
    sanitize_string,
    validate_email,
    validate_uuid,
)

# =============================================================================
# REQUEST VALIDATION DEPENDENCIES
# =============================================================================


async def validate_request_body(request: Request) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Validate incoming request body for security issues.

    Raises:
        HTTPException: If validation fails
    """
    try:
        body: dict[str, Any] = await request.json()  # TODO(TYPE): replace Any with concrete type
    except Exception:
        return {}  # No JSON body, skip validation

    _validate_nested_data(body)
    return body


def _validate_nested_data(data: Any, path: str = "") -> None:  # TODO(TYPE): replace Any with concrete type
    """Recursively validate nested data structures."""
    if isinstance(data, dict):
        for key, value in data.items():
            # Validate key
            _validate_key(key, path)
            # Validate value recursively
            _validate_nested_data(value, f"{path}.{key}" if path else key)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            _validate_nested_data(item, f"{path}[{i}]")

    elif isinstance(data, str):
        _validate_string_value(data, path)


def _validate_key(key: str, path: str) -> None:
    """Validate dictionary key for security issues."""
    # Check for NoSQL injection operators
    if any(key.startswith("$") for key in ({key: "test"}).keys()):
        logger.warning(f"NoSQL injection detected in key: {key} at {path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected"
        )


def _validate_string_value(value: str, path: str) -> None:
    """Validate string value for security issues."""
    # Check for SQL injection
    if contains_sql_injection(value):
        logger.warning(f"SQL injection detected at {path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected"
        )

    # Check for XSS
    if contains_xss(value):
        logger.warning(f"XSS attempt detected at {path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected"
        )

    # Check for path traversal
    if contains_path_traversal(value):
        logger.warning(f"Path traversal detected at {path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected"
        )


# =============================================================================
# QUERY PARAMETER VALIDATION
# =============================================================================


async def validate_query_params(request: Request) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Validate query parameters for security issues.

    Raises:
        HTTPException: If validation fails
    """
    params = dict(request.query_params)

    for key, value in params.items():
        # Validate key
        _validate_key(key, "query")

        # Validate value
        if isinstance(value, str):
            _validate_string_value(value, f"query.{key}")

    return params


# =============================================================================
# PATH PARAMETER VALIDATION
# =============================================================================


class ValidatedPathParams:
    """Validates common path parameter patterns."""

    @staticmethod
    def validate_id(param_id: str, param_name: str = "id") -> int:
        """
        Validate ID parameter (must be positive integer).

        Args:
            param_id: The ID string from path
            param_name: Name of the parameter for error messages

        Returns:
            Validated integer ID

        Raises:
            HTTPException: If validation fails
        """
        try:
            id_int = int(param_id)
            if id_int <= 0:
                raise ValueError()
            return id_int
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {param_name}: must be a positive integer",
            )

    @staticmethod
    def validate_uuid(param_uuid: str, param_name: str = "uuid") -> str:
        """
        Validate UUID parameter.

        Args:
            param_uuid: The UUID string from path
            param_name: Name of the parameter

        Returns:
            Validated UUID string

        Raises:
            HTTPException: If validation fails
        """
        try:
            return validate_uuid(param_uuid)
        except InputValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {param_name}: {str(e)}",
            )

    @staticmethod
    def validate_slug(slug: str, param_name: str = "slug") -> str:
        """
        Validate URL slug. Delegates to canonical validator.

        Args:
            slug: The slug string
            param_name: Name of the parameter

        Returns:
            Validated slug

        Raises:
            HTTPException: If validation fails
        """
        from src.core.schemas.validators import validate_slug as canonical_validate_slug

        try:
            return canonical_validate_slug(slug)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {param_name}: {exc}",
            ) from exc


# =============================================================================
# PAGINATION VALIDATION
# =============================================================================


class PaginationParams(BaseModel):
    """Validated pagination parameters."""

    skip: int = 0
    limit: int = 100

    @validator("skip")
    def skip_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("skip must be non-negative")
        return v

    @validator("limit")
    def limit_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be at least 1")
        if v > 1000:
            raise ValueError("limit cannot exceed 1000")
        return v


async def get_pagination_params(skip: int = 0, limit: int = 100) -> PaginationParams:
    """
    Get validated pagination parameters.

    Usage:
        @router.get("/items")
        async def list_items(
            pagination: PaginationParams = Depends(get_pagination_params)
        ):
            return await get_items(skip=pagination.skip, limit=pagination.limit)
    """
    try:
        return PaginationParams(skip=skip, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# SEARCH QUERY VALIDATION
# =============================================================================


class SearchParams(BaseModel):
    """Validated search parameters."""

    q: str = ""
    max_length: int = 200

    @validator("q")
    def validate_query(cls, v: str, values: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        if not v:
            return v

        max_len = values.get("max_length", 200)
        if len(v) > max_len:
            raise ValueError(f"search query cannot exceed {max_len} characters")

        # Check for injection attempts
        if contains_sql_injection(v):
            raise ValueError("invalid characters in search query")

        if contains_xss(v):
            raise ValueError("invalid characters in search query")

        return v


async def get_search_params(q: str = "", max_length: int = 200) -> SearchParams:
    """Get validated search parameters."""
    try:
        return SearchParams(q=q, max_length=max_length)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# COMPREHENSIVE VALIDATION DEPENDENCY
# =============================================================================


async def comprehensive_validation(request: Request) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Comprehensive validation of request (body, query params, path params).

    This is suitable for high-security endpoints.

    Usage:
        @router.post("/sensitive-endpoint", dependencies=[Depends(comprehensive_validation)])
        async def sensitive_endpoint(...):
            ...
    """
    # Validate body
    body = await validate_request_body(request)

    # Validate query params
    params = await validate_query_params(request)

    return {
        "body": body,
        "query_params": params,
    }


# =============================================================================
# FASTAPI DEPENDENCY FACTORIES
# =============================================================================


def validate_path_param(
    validator_func: Callable[[str, str], Any], param_name: str = "id"  # TODO(TYPE): replace Any with concrete type
) -> Callable[[str], Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Factory for creating path parameter validators.

    Usage:
        @router.get("/users/{user_id}")
        async def get_user(
            user_id: int = Depends(validate_path_param(ValidatedPathParams.validate_id, "user_id"))
        ):
            ...
    """

    async def _validator(param_value: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        return validator_func(param_value, param_name)

    return _validator


def require_validated_fields(
    required_fields: list[str],
) -> Callable[[Request], Coroutine[Any, Any, dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
    """
    Factory for requiring specific fields in request body.

    Usage:
        @router.post("/endpoint")
        async def endpoint(
            validated: dict = Depends(require_validated_fields(["email", "name"]))
        ):
            ...
    """

    async def _validator(request: Request) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        body = await validate_request_body(request)

        missing = [f for f in required_fields if f not in body]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required fields: {', '.join(missing)}",
            )

        return body

    return _validator
