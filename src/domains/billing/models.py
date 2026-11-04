"""
Local billing event log (Stripe/Mollie-agnostic).
"""

from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class BillingEvent(Base):  # type: ignore[misc]
    """Immutable billing / payment event per tenant."""

    __tablename__ = "billing_events"
    __table_args__ = (
        Index("ix_billing_events_tenant_id", "tenant_id"),
        Index("ix_billing_events_event_type", "event_type"),
        Index("ix_billing_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    event_type = mapped_column(
        String(50), nullable=False
    )  # subscription_start, payment, usage_charge
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Stripe/Mollie reference
    metadata_ = mapped_column("metadata", JSON, nullable=True)

    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<BillingEvent(id={self.id}, type={self.event_type})>"


__all__ = ["BillingEvent"]
