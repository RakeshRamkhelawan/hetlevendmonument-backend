"""
SQLAlchemy models for email campaigns (P2-006)
Provides ORM access to the 6 campaign tables created by migration 20260208_campaigns.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base

campaign_status_enum = ENUM(
    "draft",
    "scheduled",
    "sending",
    "sent",
    "paused",
    "failed",
    name="campaignstatus",
    # create_type=True (default) -- create_all(checkfirst=True) guards against duplicates.
    # Previously False but that breaks test schema creation after DROP SCHEMA CASCADE.
)


class EmailCampaign(Base):  # type: ignore[misc]
    """Email campaign with tenant isolation and soft delete."""

    __tablename__ = "email_campaigns"
    __table_args__ = (
        Index("ix_email_campaigns_tenant_id", "tenant_id"),
        Index("ix_email_campaigns_status", "status"),
        Index("ix_email_campaigns_scheduled_at", "scheduled_at"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        campaign_status_enum, nullable=False, server_default="draft"
    )
    segments: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # TODO(TYPE): replace Any with concrete type
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    segments_rel = relationship(
        "CampaignSegment", back_populates="campaign", cascade="all, delete-orphan"
    )
    analytics = relationship(
        "CampaignAnalytics",
        back_populates="campaign",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ab_tests = relationship("ABTest", back_populates="campaign", cascade="all, delete-orphan")


class CampaignSegment(Base):  # type: ignore[misc]
    """Campaign audience segment filter."""

    __tablename__ = "campaign_segments"
    __table_args__ = (
        Index("ix_campaign_segments_campaign_id", "campaign_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id = mapped_column(
        Integer, ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    filter_type: Mapped[str] = mapped_column(String(50), nullable=False)
    filter_values: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False
    )  # TODO(TYPE): replace Any with concrete type
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    campaign = relationship("EmailCampaign", back_populates="segments_rel")


class CampaignAnalytics(Base):  # type: ignore[misc]
    """Campaign delivery and engagement metrics."""

    __tablename__ = "campaign_analytics"
    __table_args__ = (
        Index("ix_campaign_analytics_campaign_id", "campaign_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id = mapped_column(
        Integer, ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bounce_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unsubscribe_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    spam_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    open_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    click_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    bounce_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    campaign = relationship("EmailCampaign", back_populates="analytics")


class ABTest(Base):  # type: ignore[misc]
    """A/B test variant for a campaign."""

    __tablename__ = "ab_tests"
    __table_args__ = (
        Index("ix_ab_tests_campaign_id", "campaign_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id = mapped_column(
        Integer, ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    variant_a_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_b_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_a_content: Mapped[str] = mapped_column(Text, nullable=False)
    variant_b_content: Mapped[str] = mapped_column(Text, nullable=False)
    split_percentage: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    winner_variant: Mapped[str | None] = mapped_column(String(1), nullable=True)
    variant_a_open_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    variant_b_open_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    variant_a_click_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    variant_b_click_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    campaign = relationship("EmailCampaign", back_populates="ab_tests")


class EmailTemplate(Base):  # type: ignore[misc]
    """Reusable email template per tenant."""

    __tablename__ = "email_templates"
    __table_args__ = (
        Index("ix_email_templates_tenant_id", "tenant_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_template: Mapped[str] = mapped_column(String(255), nullable=False)
    content_template: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UserEmailPreference(Base):  # type: ignore[misc]
    """User email subscription preferences per tenant."""

    __tablename__ = "user_email_preferences"
    __table_args__ = (
        Index("ix_user_email_preferences_user_id", "user_id"),
        Index("ix_user_email_preferences_tenant_id", "tenant_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    newsletter_subscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    marketing_subscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    events_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updates_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    unsubscribed_from: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # TODO(TYPE): replace Any with concrete type
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
