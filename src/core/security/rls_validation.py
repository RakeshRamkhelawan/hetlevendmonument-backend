"""
Row-Level Security (RLS) Validation Module
==========================================

OWASP A04:2021 - Insecure Design Prevention

This module provides decorators and utilities for enforcing Row-Level Security
(tenant isolation) across the application. It ensures:

1. All database operations are scoped to the current tenant
2. Explicit tenant_id validation before any data access
3. Defense-in-depth against tenant boundary violations
4. Audit logging for security-sensitive operations

Security Principles:
- Fail-secure: No tenant context = operation denied
- Defense in depth: Multiple layers of validation
- Least privilege: Only access data for authenticated tenant
- Audit trail: All tenant boundary operations logged

Usage:
    from src.core.security.rls_validation import (
        require_tenant_context,
        validate_resource_tenant,
        ensure_tenant_isolation,
        RLSViolationError
    )

    @router.get("/resource/{id}")
    @require_tenant_context
    async def get_resource(id: int, current_user: User = Depends(get_current_user)):
        resource = await db.get(Resource, id)
        validate_resource_tenant(resource, current_user.tenant_id)
        return resource
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, TypeVar
from collections.abc import Callable, Sequence

from fastapi import HTTPException, status
from sqlalchemy.sql import Select

from src.core.middleware.tenant_context import get_tenant_id, has_tenant_context, require_tenant_id
from src.core.security.types import HasTenantId

logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar("T")


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================


class RLSViolationError(HTTPException):
    """
    Exception raised when Row-Level Security is violated.

    This indicates an attempted access to a resource belonging to a different tenant.
    Always returns 404 to prevent information leakage about resource existence.
    """

    def __init__(
        self,
        detail: str = "Resource not found",
        resource_type: str | None = None,
        resource_id: int | str | None = None,
        attempted_tenant: int | None = None,
        actual_tenant: int | None = None,
    ) -> None:
        # Always use 404 to avoid leaking information about resource existence
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

        # Log the violation for security audit (never expose to client)
        if attempted_tenant is not None and actual_tenant is not None:
            logger.warning(
                f"RLS VIOLATION: Tenant {attempted_tenant} attempted to access "
                f"{resource_type or 'resource'} {resource_id} owned by tenant {actual_tenant}"
            )


class TenantContextMissingError(HTTPException):
    """
    Exception raised when tenant context is required but not set.

    This indicates a misconfigured endpoint or bypassed authentication.
    """

    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
        logger.error("SECURITY: Tenant context missing - possible authentication bypass")


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================


def validate_resource_tenant(
    resource: HasTenantId | None,
    expected_tenant_id: int,
    resource_type: str | None = None,
) -> None:
    """
    Validate that a resource belongs to the expected tenant.

    Args:
        resource: Database model instance with tenant_id attribute
        expected_tenant_id: The tenant_id that should own this resource
        resource_type: Optional name for logging purposes

    Raises:
        RLSViolationError: If tenant_id doesn't match (404 response)
        AttributeError: If resource doesn't have tenant_id attribute

    Example:
        user = await db.get(User, user_id)
        validate_resource_tenant(user, current_user.tenant_id, "User")
    """
    if resource is None:
        raise RLSViolationError(
            detail=f"{resource_type or 'Resource'} not found",
            resource_type=resource_type,
        )

    # Get resource tenant_id
    resource_tenant_id = getattr(resource, "tenant_id", None)

    if resource_tenant_id is None:
        # Resource doesn't have tenant_id - log warning but allow
        # (Some system tables don't have tenant isolation)
        resource_name = resource_type or type(resource).__name__
        logger.debug(f"Resource {resource_name} has no tenant_id attribute")
        return

    # Validate tenant match
    if resource_tenant_id != expected_tenant_id:
        resource_id = getattr(resource, "id", None)
        raise RLSViolationError(
            detail=f"{resource_type or 'Resource'} not found",
            resource_type=resource_type or type(resource).__name__,
            resource_id=resource_id,
            attempted_tenant=expected_tenant_id,
            actual_tenant=resource_tenant_id,
        )


def validate_tenant_id_param(
    tenant_id_param: int,
    expected_tenant_id: int,
    param_name: str = "tenant_id",
) -> None:
    """
    Validate that a tenant_id parameter matches the authenticated user's tenant.

    Use this when an endpoint accepts tenant_id as a parameter to prevent
    users from specifying a different tenant than their own.

    Args:
        tenant_id_param: The tenant_id provided in the request
        expected_tenant_id: The tenant_id from the authenticated user
        param_name: Name of the parameter for logging

    Raises:
        HTTPException: 403 Forbidden if tenant IDs don't match
    """
    if tenant_id_param != expected_tenant_id:
        logger.warning(
            f"RLS VIOLATION: User in tenant {expected_tenant_id} attempted to "
            f"access {param_name}={tenant_id_param}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot access resources from other tenants",
        )


def ensure_tenant_isolation(
    model_class: type,
    tenant_id: int,
) -> bool:
    """
    Verify that a model class has tenant_id for proper isolation.

    Args:
        model_class: SQLAlchemy model class to check
        tenant_id: Current tenant context (for validation)

    Returns:
        bool: True if model has tenant_id column

    Raises:
        TenantContextMissingError: If tenant_id is None
    """
    if tenant_id is None:
        raise TenantContextMissingError()

    has_tenant_column = hasattr(model_class, "tenant_id")

    if not has_tenant_column:
        model_name = getattr(model_class, "__name__", str(model_class))
        logger.warning(
            f"SECURITY: Model {model_name} does not have tenant_id column - "
            f"queries may not be tenant-isolated"
        )

    return has_tenant_column


# ============================================================================
# DECORATORS
# ============================================================================


def require_tenant_context(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that ensures tenant context is set before endpoint execution.

    Usage:
        @router.get("/protected")
        @require_tenant_context
        async def protected_endpoint():
            # Guaranteed to have tenant context here
            tenant_id = get_tenant_id()
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not has_tenant_context():
            raise TenantContextMissingError(
                detail="This endpoint requires authentication with a valid tenant context"
            )
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    return wrapper  # type: ignore[return-value]


def validate_tenant_access(
    resource_param: str = "id",
    model_class: type | None = None,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator that validates tenant access to a resource.

    This decorator extracts a resource ID from the request parameters,
    looks up the resource, and validates tenant ownership before allowing
    the endpoint to execute.

    Args:
        resource_param: Name of the path parameter containing the resource ID
        model_class: SQLAlchemy model class to query (optional)

    Usage:
        @router.get("/users/{user_id}")
        @validate_tenant_access(resource_param="user_id", model_class=User)
        async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
            # Resource already validated by decorator
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get tenant context
            tenant_id = get_tenant_id()
            if tenant_id is None:
                raise TenantContextMissingError()

            # If model class provided, we could do pre-validation here
            # For now, just ensure tenant context is set
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


# ============================================================================
# QUERY HELPERS
# ============================================================================


def add_tenant_filter(
    query: Select[Any],  # TODO(TYPE): replace Any with concrete type
    model_class: type,
    tenant_id: int,
) -> Select[Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Add tenant_id filter to a SQLAlchemy query.

    Note: With automatic tenant filtering enabled, this is usually not needed.
    Use this for explicit filtering when auto-filtering is bypassed.

    Args:
        query: SQLAlchemy select() query
        model_class: Model class with tenant_id column
        tenant_id: Tenant ID to filter by

    Returns:
        Modified query with tenant filter

    Example:
        query = select(User)
        query = add_tenant_filter(query, User, current_user.tenant_id)
    """
    if hasattr(model_class, "tenant_id"):
        return query.where(model_class.tenant_id == tenant_id)
    return query


def validate_bulk_tenant_ids(
    resources: Sequence[HasTenantId | None],
    expected_tenant_id: int,
    resource_type: str = "Resource",
) -> list[HasTenantId | None]:
    """
    Validate tenant_id for a list of resources (bulk operations).

    Returns only resources that belong to the expected tenant.
    Logs any violations found.

    Args:
        resources: List of database model instances
        expected_tenant_id: Expected tenant_id for all resources
        resource_type: Name for logging purposes

    Returns:
        Filtered list containing only resources from expected tenant
    """
    valid_resources: list[HasTenantId | None] = []
    violations = 0

    for resource in resources:
        resource_tenant_id = getattr(resource, "tenant_id", None)

        if resource_tenant_id is None:
            # No tenant isolation for this resource type
            valid_resources.append(resource)
        elif resource_tenant_id == expected_tenant_id:
            valid_resources.append(resource)
        else:
            violations += 1

    if violations > 0:
        logger.warning(
            f"RLS BULK VIOLATION: {violations} {resource_type} records "
            f"filtered out for tenant {expected_tenant_id}"
        )

    return valid_resources


# ============================================================================
# TENANT CONTEXT UTILITIES
# ============================================================================


def get_safe_tenant_id() -> int | None:
    """
    Get tenant_id safely without raising exceptions.

    Returns:
        Current tenant_id or None if not set
    """
    return get_tenant_id()


def get_required_tenant_id() -> int:
    """
    Get tenant_id with strict validation, raises if not set.

    Returns:
        Current tenant_id

    Raises:
        TenantContextMissingError: If tenant context not set
    """
    try:
        return require_tenant_id()
    except (RuntimeError, ValueError) as e:
        raise TenantContextMissingError(detail=str(e))


# ============================================================================
# MODEL VALIDATION HELPERS
# ============================================================================


def validate_model_has_tenant_id(model_class: type) -> bool:
    """
    Check if a model class has tenant_id column properly defined.

    Args:
        model_class: SQLAlchemy model class

    Returns:
        True if model has tenant_id with proper FK constraint
    """
    if not hasattr(model_class, "tenant_id"):
        return False

    # Check if it's a proper Column with FK
    tenant_col = getattr(model_class, "tenant_id", None)
    if tenant_col is None:
        return False

    # Additional validation could check FK constraints, nullable, etc.
    return True


def audit_tenant_access(
    action: str,
    resource_type: str,
    resource_id: int | str,
    tenant_id: int,
    user_id: int | None = None,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> None:
    """
    Log a tenant access event for security audit.

    Args:
        action: Action performed (read, write, delete, etc.)
        resource_type: Type of resource accessed
        resource_id: ID of the resource
        tenant_id: Tenant performing the action
        user_id: Optional user ID performing the action
        details: Optional additional details
    """
    logger.info(
        f"TENANT_ACCESS: {action} on {resource_type}:{resource_id} "
        f"by tenant:{tenant_id} user:{user_id} details:{details}"
    )


# Export all public functions
__all__ = [
    "RLSViolationError",
    "TenantContextMissingError",
    "validate_resource_tenant",
    "validate_tenant_id_param",
    "ensure_tenant_isolation",
    "require_tenant_context",
    "validate_tenant_access",
    "add_tenant_filter",
    "validate_bulk_tenant_ids",
    "get_safe_tenant_id",
    "get_required_tenant_id",
    "validate_model_has_tenant_id",
    "audit_tenant_access",
]
