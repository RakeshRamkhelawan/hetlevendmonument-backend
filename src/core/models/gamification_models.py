"""
Gamification Models - Points, Badges, and Achievements
Feature 5: User engagement through gamification.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class UserPoints(Base):  # type: ignore[misc]
    """Tracks user points for gamification."""

    __tablename__ = "user_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Point totals
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Streak tracking
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_user_points_user_tenant", "user_id", "tenant_id", unique=True),
        Index("ix_user_points_tenant_level", "tenant_id", "level"),
    )


class Badge(Base):  # type: ignore[misc]
    """Available badges that users can earn."""

    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Badge info
    code: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "first_workflow", "power_user"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Icon name or emoji
    color: Mapped[str | None] = mapped_column(String(20), default="#3B82F6")  # Hex color

    # Requirements
    points_required: Mapped[int | None] = mapped_column(Integer, default=0)
    is_secret: Mapped[bool | None] = mapped_column(Boolean, default=False)  # Hidden until earned

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_badges_tenant_code", "tenant_id", "code", unique=True),)


class UserBadge(Base):  # type: ignore[misc]
    """Junction table for earned badges."""

    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    badge_id = mapped_column(Integer, ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    earned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_user_badges_user_badge", "user_id", "badge_id", unique=True),
        Index("ix_user_badges_tenant", "tenant_id"),
    )


class PointTransaction(Base):  # type: ignore[misc]
    """History of point changes for audit trail."""

    __tablename__ = "point_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Transaction details
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # Positive or negative
    action = mapped_column(String(50), nullable=False)  # e.g., "workflow_completed", "badge_earned"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_point_transactions_user", "user_id"),
        Index("ix_point_transactions_tenant", "tenant_id"),
    )
