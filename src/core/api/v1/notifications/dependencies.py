"""Notifications domain dependencies (ADR-033 Laag 1)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db as get_db  # noqa: F401
from src.core.governance.audit import audit_service as audit_service  # noqa: F401
from src.core.models.rbac_models import User
from .service import NotificationsService as NotificationsService  # noqa: F401


def get_notifications_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationsService:
    return NotificationsService(db=db, tenant_id=current_user.tenant_id, user_id=current_user.id)
