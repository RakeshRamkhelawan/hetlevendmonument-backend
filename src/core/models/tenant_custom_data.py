"""
EAV-style custom data store per tenant.
Allows tenants to store arbitrary key-value pairs without schema changes.
"""

from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class TenantCustomData(Base):  # type: ignore[misc]
    """Key-value store scoped by tenant + namespace."""

    __tablename__ = "tenant_custom_data"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "key", name="uq_tenant_custom_data"),
        Index("ix_tenant_custom_data_tenant_ns", "tenant_id", "namespace"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    namespace = mapped_column(String(100), nullable=False)  # e.g. 'branding', 'workflow_defaults'
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)  # TODO(TYPE): replace Any with concrete type

    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<TenantCustomData(tenant={self.tenant_id}, {self.namespace}.{self.key})>"


__all__ = ["TenantCustomData"]
