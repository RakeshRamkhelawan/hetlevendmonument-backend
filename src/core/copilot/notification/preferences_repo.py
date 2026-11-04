"""
Repository for User Notification Preferences.
"""

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import Boolean, Column, DateTime, Integer, SmallInteger, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.copilot.notification.models import NotificationPreferences
from src.core.database.database import Base


class UserNotificationPreferencesRow(Base):  # type: ignore[misc]
    __tablename__ = "user_notification_preferences"

    user_id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False)
    daily_limit = Column(Integer, nullable=False, server_default="25")
    delivery_mode = Column(String(16), nullable=False, server_default="individual")
    critical_always_immediate = Column(Boolean, nullable=False, server_default="true")
    quiet_hours_start = Column(SmallInteger, nullable=True)
    quiet_hours_end = Column(SmallInteger, nullable=True)
    quiet_hours_timezone = Column(String(63), nullable=False, server_default="UTC")
    updated_at = Column(DateTime(timezone=True), nullable=False)


def _to_dataclass(row: UserNotificationPreferencesRow) -> NotificationPreferences:
    return NotificationPreferences(
        user_id=cast(int, row.user_id),
        tenant_id=cast(int, row.tenant_id),
        daily_limit=cast(int, row.daily_limit),
        delivery_mode=cast(str, row.delivery_mode),  # type: ignore[arg-type]
        critical_always_immediate=cast(bool, row.critical_always_immediate),
        quiet_hours_start=cast(int | None, row.quiet_hours_start),
        quiet_hours_end=cast(int | None, row.quiet_hours_end),
        quiet_hours_timezone=cast(str | None, row.quiet_hours_timezone),
        updated_at=cast(datetime | None, row.updated_at),
    )


class UserNotificationPreferencesRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_user(self, user_id: int, tenant_id: int) -> NotificationPreferences:
        """Return preferences voor user, of defaults bij ontbreken."""
        # ORM hook injecteert tenant filter automatisch (ADR-004),
        # maar voor expliciete duidelijkheid voegen we het toe.
        result = await self._db.execute(
            select(UserNotificationPreferencesRow).where(
                UserNotificationPreferencesRow.user_id == user_id,
                UserNotificationPreferencesRow.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return NotificationPreferences(user_id=user_id, tenant_id=tenant_id)
        return _to_dataclass(row)

    async def upsert(self, prefs: NotificationPreferences) -> None:
        # PostgreSQL ON CONFLICT (user_id) DO UPDATE is typical but simpler implementation with merge
        # for SQLite compatibility in tests if needed. For now using merge.
        row = UserNotificationPreferencesRow(
            user_id=prefs.user_id,
            tenant_id=prefs.tenant_id,
            daily_limit=prefs.daily_limit,
            delivery_mode=prefs.delivery_mode,
            critical_always_immediate=prefs.critical_always_immediate,
            quiet_hours_start=prefs.quiet_hours_start,
            quiet_hours_end=prefs.quiet_hours_end,
            quiet_hours_timezone=prefs.quiet_hours_timezone or "UTC",
            updated_at=prefs.updated_at or datetime.now(timezone.utc),
        )
        await self._db.merge(row)
        await self._db.commit()
