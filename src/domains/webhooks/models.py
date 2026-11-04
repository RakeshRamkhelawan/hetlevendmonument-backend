"""
Outbound webhook models: endpoint subscriptions and delivery tracking.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class WebhookEndpoint(Base):  # type: ignore[misc]
    """Outbound webhook subscription per tenant."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index("ix_webhook_endpoints_tenant_id", "tenant_id"),
        Index("ix_webhook_endpoints_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)  # HMAC signing secret
    events: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False
    )  # ["workflow.complete", "agent.error"]
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<WebhookEndpoint(id={self.id}, url={self.url[:40]})>"


class WebhookDelivery(Base):  # type: ignore[misc]
    """Individual delivery attempt for a webhook event."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_webhook_id", "webhook_id"),
        Index("ix_webhook_deliveries_tenant_id", "tenant_id"),
        Index("ix_webhook_deliveries_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    webhook_id = mapped_column(
        Integer, ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False)  # TODO(TYPE): replace Any with concrete type

    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)  # HTTP status
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, event={self.event_type})>"


__all__ = ["WebhookEndpoint", "WebhookDelivery"]
