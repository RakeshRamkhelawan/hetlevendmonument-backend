import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base


class ChannelType(str, enum.Enum):
    """Available messaging channels."""

    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    DISCORD = "discord"


class TenantIntegration(Base):  # type: ignore[misc]
    """
    Tenant-specific integration settings for messaging channels and external providers.
    Ensures multi-tenant security for bot tokens and API keys.
    """

    __tablename__ = "tenant_integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Store channel type as string but use the Enum for logic
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Integration Credentials
    bot_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Telegram Bot Token or Slack Bot Token
    webhook_secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # X-Telegram-Bot-Api-Secret-Token

    # Flexible configuration for provider-specific fields (e.g., Twilio SID, WhatsApp Number)
    provider_config: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Indexing
    __table_args__ = (
        Index("idx_integration_tenant_channel", "tenant_id", "channel_type", unique=True),
    )

    def __repr__(self) -> str:
        return f"<TenantIntegration(id={self.id}, tenant_id={self.tenant_id}, channel='{self.channel_type}')>"
