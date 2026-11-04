# orphan:exempt reason: Laag 1 dependencies, imported by canvas sub-routers (ADR-033)
"""Canvas API shared dependencies (ADR-033 Laag 1)."""

from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_current_user as get_current_user
from src.core.database.database import get_db as get_db
from src.core.middleware.tenant_context import get_current_tenant_id as get_current_tenant_id
from src.domains.canvas.service import CanvasService


def get_canvas_service(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> CanvasService:
    """Dependency factory for CanvasService."""
    return CanvasService(db=db, tenant_id=tenant_id, user_id=current_user.id)
