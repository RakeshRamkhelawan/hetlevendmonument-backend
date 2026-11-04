"""
Threaded comments / notes on any entity.
"""


from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class Comment(Base):  # type: ignore[misc]
    """User comment on any tenant-scoped entity. Supports threading."""

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_entity", "entity_type", "entity_id"),
        Index("ix_comments_tenant_id", "tenant_id"),
        Index("ix_comments_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    entity_type = mapped_column(String(50), nullable=False)  # 'agent', 'workflow', 'document', ...
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id = mapped_column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<Comment(id={self.id}, entity={self.entity_type}:{self.entity_id})>"


__all__ = ["Comment"]
