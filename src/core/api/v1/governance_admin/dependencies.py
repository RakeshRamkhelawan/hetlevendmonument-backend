"""Shared dependency functions for governance_admin endpoints."""

from typing import Any

from fastapi import HTTPException, status

from src.core.middleware.tenant_context import get_current_tenant_id


async def get_tenant() -> int:
    """Get tenant ID with error handling."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


def get_user_id(current_user: Any) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user (dict or object)."""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"
