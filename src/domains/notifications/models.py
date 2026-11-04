"""
Notification models for in-app notification inbox.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class Notification(Base):  # type: ignore[misc]
    """Persistent notification for user inbox."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_user", "tenant_id", "user_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    type = mapped_column(String(50), nullable=False)  # 'workflow_complete', 'agent_error', 'system'
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # Arbitrary payload (link, entity ref, etc.)
    channel = mapped_column(
        String(20), nullable=False, server_default="in_app"
    )  # 'in_app','email','push'

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("(CURRENT_TIMESTAMP)")
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.type})>"


__all__ = ["Notification"]
