"""
Tenant Context Management
Thread-safe storage of current tenant_id for request lifecycle

CRITICAL SECURITY COMPONENT:
- Uses ContextVar for async-safe isolation between requests
- Prevents cross-tenant data leaks
- Validates all tenant_id values to prevent SQL injection (P5.1.3)

Design:
- Middleware extracts tenant_id from JWT token
- Stores in ContextVar (inherited by all async tasks in request)
- Database queries automatically filtered by tenant_id
- Impossible to forget tenant filter = zero data leak risk

P5.1.3 Security Enhancement:
- Integrated with input_sanitization module for SQL injection prevention
- Strict type coercion validation
- Audit logging for suspicious tenant_id values
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

from fastapi import Depends, HTTPException, status
from loguru import logger

# ============================================================================
# SQL INJECTION PATTERN DETECTION (P5.1.3)
# ============================================================================

# Patterns that should NEVER appear in a tenant_id string representation
_SQL_INJECTION_PATTERNS = [
    re.compile(r"--"),  # SQL comment
    re.compile(r"/\*"),  # Block comment start
    re.compile(r"\bOR\b", re.IGNORECASE),  # OR keyword
    re.compile(r"\bAND\b", re.IGNORECASE),  # AND keyword
    re.compile(r'[\'";]'),  # Quote characters
    re.compile(r"\bUNION\b", re.IGNORECASE),  # UNION keyword
    re.compile(r"\bSELECT\b", re.IGNORECASE),  # SELECT keyword
    re.compile(r"\bDROP\b", re.IGNORECASE),  # DROP keyword
    re.compile(r"\bDELETE\b", re.IGNORECASE),  # DELETE keyword
    re.compile(r"\bINSERT\b", re.IGNORECASE),  # INSERT keyword
    re.compile(r"\bUPDATE\b", re.IGNORECASE),  # UPDATE keyword
    re.compile(r"="),  # Equals sign (comparison injection)
]


def _detect_injection_in_value(value: object) -> str | None:
    """
    Detect SQL injection patterns in a value that should be tenant_id.

    Returns:
        None if safe, error message string if injection detected
    """
    if value is None:
        return None

    # Convert to string for pattern checking
    str_value = str(value)

    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(str_value):
            return f"SQL injection pattern detected: {pattern.pattern}"

    return None


# ============================================================================
# CONTEXT VARIABLES - Thread-safe tenant tracking
# ============================================================================

# Global ContextVar for storing current tenant_id
# Type: int (database primary key for tenants table)
_tenant_context: ContextVar[int | None] = ContextVar("tenant_id", default=None)

# Global ContextVar for storing current user's JWT scopes (for fast permission checks)
# Type: List[str] (OAuth2 scopes in resource:action format)
_current_user_scopes: ContextVar[list[str]] = ContextVar("user_scopes", default=[])


def set_tenant_id(tenant_id: int | str | None) -> None:
    """
    Set tenant ID for current async context with strict security validation.

    Args:
        tenant_id: Positive integer tenant identifier (or numeric string)

    Raises:
        TypeError: If tenant_id is not an integer or numeric string
        ValueError: If tenant_id is not positive or contains injection patterns

    Security Features (P5.1.3):
    - Type validation prevents SQL injection via type confusion
    - Pattern detection catches embedded SQL commands
    - Range validation prevents negative/zero tenant IDs
    - Logs all context changes for audit trail
    - Rejects non-numeric strings that could contain payloads

    Usage:
        # In middleware
        set_tenant_id(payload['tenant_id'])
    """
    # Allow None for testing scenarios
    if tenant_id is None:
        _tenant_context.set(None)
        return

    # Type validation FIRST (P5.1.3: prevents injection via type confusion)
    if isinstance(tenant_id, str):
        stripped = tenant_id.strip()
        if not stripped:
            raise ValueError("tenant_id must be numeric and non-empty")

        injection_error = _detect_injection_in_value(stripped)
        if injection_error:
            logger.critical(
                f"SECURITY: SQL injection attempt in tenant_id! "
                f"value={stripped[:50]}, error={injection_error}"
            )
            raise ValueError(
                f"tenant_id rejected: {injection_error}. This security event has been logged."
            )

        if not stripped.isdigit():
            logger.warning(f"SECURITY: Non-numeric tenant_id string rejected: {stripped[:50]}")
            raise ValueError("tenant_id must be numeric")

        tenant_id = int(stripped)

    # P5.1.3: Check for injection patterns BEFORE any conversion
    injection_error = _detect_injection_in_value(tenant_id)
    if injection_error:
        logger.critical(
            f"SECURITY: SQL injection attempt in tenant_id! "
            f"value={str(tenant_id)[:50]}, error={injection_error}"
        )
        raise ValueError(
            f"tenant_id rejected: {injection_error}. This security event has been logged."
        )

    # Type validation
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool):
        logger.warning(f"SECURITY: Invalid tenant_id type: {type(tenant_id).__name__}")
        raise TypeError(
            f"tenant_id must be int, got {type(tenant_id).__name__}. "
            "This may indicate a token tampering attempt."
        )

    # Range validation
    if tenant_id <= 0:
        raise ValueError(
            f"tenant_id must be positive, got {tenant_id}. Invalid tenant IDs are rejected."
        )

    # Additional max value check to prevent overflow attacks
    if tenant_id > 2147483647:  # Max 32-bit signed int
        raise ValueError(
            f"tenant_id exceeds maximum value: {tenant_id}. Integer overflow attack suspected."
        )

    _tenant_context.set(tenant_id)
    logger.debug(f"Tenant context set: tenant_id={tenant_id}")


def get_tenant_id() -> int | None:
    """
    Get current tenant ID from context.

    Returns:
        int: Current tenant ID, or None if not set

    Note: Returns None for public endpoints (no tenant context required)

    Usage:
        tenant_id = get_tenant_id()
        if tenant_id:
            # Filter by tenant
            query = query.filter(Model.tenant_id == tenant_id)
    """
    return _tenant_context.get()


def clear_tenant_context() -> None:
    """
    Clear tenant context.

    Called by middleware in finally block to prevent context leaks
    between requests. CRITICAL for security - ensures no tenant context
    bleeds between different requests.

    Usage:
        # In middleware finally block
        try:
            # Process request
            pass
        finally:
            clear_tenant_context()
    """
    _tenant_context.set(None)
    logger.debug("Tenant context cleared")


def require_tenant_id() -> int:
    """
    Get tenant ID with strict validation.
    Use in database queries to enforce tenant isolation.

    Returns:
        int: Validated tenant ID

    Raises:
        RuntimeError: If tenant context not set (security issue)
        ValueError: If tenant_id invalid (possible breach)

    Security Features:
    - Fails immediately if no tenant context (fail-secure)
    - Type validation (prevents SQL injection)
    - Range validation (no negative/zero IDs)
    - Defense in depth (validates again after retrieval)

    Usage:
        # In database query
        tenant_id = require_tenant_id()
        query = select(User).where(User.tenant_id == tenant_id)

    Example Error Scenarios:
    - Public endpoint tries to access tenant data -> RuntimeError
    - JWT missing tenant_id claim -> RuntimeError
    - Tampered tenant_id in context -> ValueError
    """
    tenant_id = get_tenant_id()

    # Fail-secure: No tenant context = critical security issue
    if tenant_id is None:
        raise RuntimeError(
            "Tenant context not set. Critical security issue - "
            "all queries MUST have tenant context. "
            "This indicates middleware failure or bypassed authentication."
        )

    # SECURITY: Re-validate to prevent tampering
    # (Defense in depth - validate even though set_tenant_id already validated)
    if not isinstance(tenant_id, int) or tenant_id <= 0:
        raise ValueError(
            f"Invalid tenant_id in context: {tenant_id}. "
            "Possible security breach detected. "
            "Tenant context may have been corrupted."
        )

    return tenant_id


def get_current_tenant_id() -> int | None:
    """
    Deprecated alias for get_tenant_id().
    """
    return _tenant_context.get()


def safe_get_tenant_id(tenant_id: int | None = Depends(get_tenant_id)) -> int:
    """
    Architectural Fix: Robuuste dependency voor endpoints die strikt een tenant vereisen.
    Converteert expliciet naar int en voorkomt NoneType crashes in Pydantic.
    """
    if tenant_id is None:
        logger.error(
            "CRITICAL: Tenant ID missing in authenticated context (Architecture Violation)"
        )
        # Fallback for dev/testing if needed (optional, but requested in incident)
        # Uncomment below line if desperate fallback is needed
        # return 1
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required for this operation",
        )
    try:
        return int(tenant_id)
    except (ValueError, TypeError):
        logger.error(f"CRITICAL: Tenant ID format error. Got: {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant ID format"
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def has_tenant_context() -> bool:
    """
    Check if tenant context is set.

    Returns:
        bool: True if tenant context is set, False otherwise

    Usage:
        if has_tenant_context():
            # Safe to access tenant-scoped resources
            data = get_tenant_data()
        else:
            # Public endpoint - return global data
            data = get_public_data()
    """
    return get_tenant_id() is not None


def get_tenant_context_info() -> dict[str, str | bool | int | None]:
    """
    Get tenant context information for debugging/logging.

    Returns:
        dict: Tenant context information

    Usage:
        logger.info("Request context", extra=get_tenant_context_info())
    """
    tenant_id = get_tenant_id()
    return {
        "has_tenant_context": tenant_id is not None,
        "tenant_id": tenant_id,
        "tenant_id_type": type(tenant_id).__name__ if tenant_id is not None else None,
    }
