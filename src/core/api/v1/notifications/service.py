# dsm:exempt -- audit_service is a cross-cutting infrastructure singleton; injecting via Depends adds coupling without benefit
"""
Notifications service -- encapsulates all DB access for the notification router (ADR-033).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.audit import audit_service
from src.core.utils.best_effort import best_effort
from src.domains.notifications.models import Notification

logger = logging.getLogger(__name__)


class NotificationsService:
    def __init__(self, db: AsyncSession, tenant_id: int, user_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def list_notifications(
        self,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        stmt = select(Notification).where(
            Notification.tenant_id == self.tenant_id,
            Notification.user_id == self.user_id,
        )
        if unread_only:
            stmt = stmt.where(~Notification.is_read)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.offset(offset).limit(limit).order_by(Notification.created_at.desc())
        result = await self.db.execute(stmt)
        notifications = result.scalars().all()
        return {"items": notifications, "total": total}

    async def mark_all_read(self) -> int:
        stmt = select(Notification).where(
            Notification.tenant_id == self.tenant_id,
            Notification.user_id == self.user_id,
            ~Notification.is_read,
        )
        result = await self.db.execute(stmt)
        unread = result.scalars().all()

        now = datetime.now(timezone.utc)
        for n in unread:
            n.is_read = True
            n.read_at = now
        await self.db.commit()

        async with best_effort("notification bulk read audit", db_session=self.db):
            await audit_service.log_action(
                tenant_id=self.tenant_id,
                action="notification.mark_all_read",
                resource=f"user:{self.user_id}",
                user_id=self.user_id,
                details={"count": len(unread)},
                session=self.db,
            )
        return len(unread)

    async def mark_single_read(self, notification_id: int) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == self.tenant_id,
            Notification.user_id == self.user_id,
        )
        result = await self.db.execute(stmt)
        notif = result.scalar_one_or_none()
        if notif is None:
            return None

        if not notif.is_read:
            notif.is_read = True
            notif.read_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(notif)

            async with best_effort("notification read audit", db_session=self.db):
                await audit_service.log_action(
                    tenant_id=self.tenant_id,
                    action="notification.mark_read",
                    resource=f"notification:{notif.id}",
                    user_id=self.user_id,
                    details={},
                    session=self.db,
                )
        return notif
