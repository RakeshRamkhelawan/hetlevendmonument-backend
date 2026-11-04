"""Synthesis domain dependencies (ADR-033 Laag 1)."""

from fastapi import HTTPException, status

from src.core.middleware.tenant_context import get_current_tenant_id


async def get_tenant() -> int:
    """Get tenant ID from JWT context with error handling."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id
