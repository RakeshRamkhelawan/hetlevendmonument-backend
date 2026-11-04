"""
Polymorphic tagging system: tags + entity_tags junction.
Any tenant-scoped entity can be tagged.  # TODO(TYPE): replace Any with concrete type
"""

from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class Tag(Base):  # type: ignore[misc]
    """Tenant-scoped tag definition."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
        Index("ix_tags_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(
        String(7), nullable=True
    )  # Hex colour e.g. #FF5733
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name={self.name})>"


class EntityTag(Base):  # type: ignore[misc]
    """Polymorphic junction: links a tag to any entity type.

    NEO AUDIT FIX (P0): Added tenant_id for multi-tenant isolation.
    Without this, queries on EntityTag by entity_id alone leak cross-tenant data.
    """

    __tablename__ = "entity_tags"
    __table_args__ = (
        UniqueConstraint("tag_id", "entity_type", "entity_id", name="uq_entity_tags_unique"),
        Index("ix_entity_tags_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = mapped_column(String(50), nullable=False)  # 'agent', 'workflow', 'document', ...
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<EntityTag(tag={self.tag_id}, {self.entity_type}:{self.entity_id})>"


__all__ = ["Tag", "EntityTag"]
