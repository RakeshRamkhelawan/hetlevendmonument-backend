"""
User Helper Functions for API Endpoints
========================================

Provides safe attribute extraction from current_user objects to prevent
SQLAlchemy session lifecycle issues.

CRITICAL: These functions prevent "Could not refresh instance User" errors
by safely extracting attributes without triggering lazy-loaded relationships
or expired session attributes.
"""

from typing import Any, cast


def get_user_id(current_user: Any) -> int | None:  # TODO(TYPE): replace Any with concrete type
    """
    Safely extract user ID from current_user (handles dict, UserResponse, and User objects)

    CRITICAL FIX: Prevents SQLAlchemy session refresh errors by using safe attribute access.

    Handles multiple input formats:
    - UserResponse object (has .id attribute)
    - Dict with "user_id" or "id" key
    - User ORM object (safely extracts .id without triggering lazy loads)

    Args:
        current_user: User object, UserResponse, or dict containing user data

    Returns:
        User ID as integer, or None if not found
    """
    # Try object attribute access first (UserResponse, User ORM)
    if hasattr(current_user, "id"):
        # Use getattr with None default to avoid triggering lazy loads
        user_id: int | None = getattr(current_user, "id", None)
        if user_id is not None:
            return user_id

    # Try dict access (JWT payload format)
    if isinstance(current_user, dict):
        # Try both "user_id" and "id" keys
        result: int | None = current_user.get("user_id") or current_user.get("id")
        return result

    return None


def get_user_email(current_user: Any) -> str | None:  # TODO(TYPE): replace Any with concrete type
    """
    Safely extract user email from current_user

    Args:
        current_user: User object, UserResponse, or dict containing user data

    Returns:
        User email as string, or None if not found
    """
    # Try object attribute access
    if hasattr(current_user, "email"):
        email: str | None = getattr(current_user, "email", None)
        if email is not None:
            return email

    # Try dict access
    if isinstance(current_user, dict):
        email_result: str | None = current_user.get("email")
        return email_result

    return None


def get_user_tenant_id(current_user: Any) -> int | None:  # TODO(TYPE): replace Any with concrete type
    """
    Safely extract tenant ID from current_user

    Args:
        current_user: User object, UserResponse, or dict containing user data

    Returns:
        Tenant ID as integer, or None if not found
    """
    # Try object attribute access
    if hasattr(current_user, "tenant_id"):
        tenant_id: int | None = getattr(current_user, "tenant_id", None)
        if tenant_id is not None:
            return tenant_id

    # Try dict access
    if isinstance(current_user, dict):
        tenant_result: int | None = current_user.get("tenant_id")
        return tenant_result

    return None


def get_user_role_id(current_user: Any) -> int | None:  # TODO(TYPE): replace Any with concrete type
    """
    Safely extract role ID from current_user

    Args:
        current_user: User object, UserResponse, or dict containing user data

    Returns:
        Role ID as integer, or None if not found
    """
    # Try object attribute access
    if hasattr(current_user, "role_id"):
        role_id: int | None = getattr(current_user, "role_id", None)
        if role_id is not None:
            return role_id

    # Try dict access
    if isinstance(current_user, dict):
        role_result: int | None = current_user.get("role_id")
        return role_result

    return None
