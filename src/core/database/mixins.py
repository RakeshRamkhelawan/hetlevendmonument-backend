"""
Database Mixins

Reusable SQLAlchemy model mixins for common patterns.

Part of SD-8.1 implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns.
    """

    __allow_unmapped__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Mixin for soft delete functionality.

    Adds deleted_at column for logical deletes.
    Records are not removed from DB, just marked as deleted.

    Usage:
        class User(Base, SoftDeleteMixin):
            ...

        # Soft delete
        user.soft_delete()

        # Query non-deleted
        query.filter(User.deleted_at.is_(None))
    """

    __allow_unmapped__ = True

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def soft_delete(self) -> None:
        """Mark record as deleted."""
        self.deleted_at = datetime.now(timezone.utc)
        self.is_deleted = True

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.is_deleted = False


class AuditMixin(TimestampMixin):
    """
    Extended audit mixin with created_by and updated_by user tracking.
    """

    __allow_unmapped__ = True

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
