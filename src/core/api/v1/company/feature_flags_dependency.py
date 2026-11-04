"""Dependencies for company-layer feature gating."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status

from src.core.api.dependencies import require_authenticated_user
from src.core.company.feature_flags import is_company_layer_enabled


async def require_company_layer_enabled(
    current_user: dict[str, Any] = Depends(require_authenticated_user),  # TODO(TYPE): replace Any with concrete type
) -> None:
    """Fail closed with 404 when company layer is disabled for tenant."""
    if isinstance(current_user, dict):
        tenant_id = current_user.get("tenant_id")
    else:
        tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company layer is not enabled for this tenant",
        )

    if not is_company_layer_enabled(int(tenant_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company layer is not enabled for this tenant",
        )
