"""
Document storage metadata models.
Tracks uploaded files with storage-backend agnostic references.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class Document(Base):  # type: ignore[misc]
    """File/document metadata (storage-backend agnostic)."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_uploaded_by", "uploaded_by"),
        Index("ix_documents_mime_type", "mime_type"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_deleted_at", "deleted_at"),
        # NOTE: GIN fulltext index is PostgreSQL-only and maintained via Alembic
        # migration 93475c4a00a0. It is intentionally NOT listed here to keep
        # SQLite unit tests working (to_tsvector is not available in SQLite).
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    storage_backend = mapped_column(
        String(20), nullable=False, server_default="local"
    )  # local, s3, azure
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    metadata_ = mapped_column(
        "metadata", JSON, nullable=True
    )  # Extra structured info (tags, description, ...)

    # Deprecated: is_deleted is replaced by deleted_at for soft delete.
    # Kept for backward compatibility during migration period.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # New fields for SP-B01
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
    )  # pending, processing, ready, error
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    content: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename})>"


class DocumentVersion(Base):  # type: ignore[misc]
    """Snapshot of a document at a specific version."""

    __tablename__ = "document_versions"
    __table_args__ = (
        Index("ix_document_versions_document_id", "document_id"),
        Index("ix_document_versions_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )

    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
        onupdate=text("clock_timestamp()"),
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, document_id={self.document_id}, version={self.version})>"


__all__ = ["Document", "DocumentVersion"]
