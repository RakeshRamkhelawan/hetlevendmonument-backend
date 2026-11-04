"""
Digital Twin Models -- SQLAlchemy ORM models voor de Practical Digital Twin.

Tabellen:
- user_behavior_observations: Geanonimiseerde gedragsobservaties per user
- user_cognitive_profiles: Geleerde cognitieve profielen per user
- user_twin_consent: GDPR consent + opt-out state per user

Gebruik:
    from src.core.learning.twin_models import (
        UserBehaviorObservation,
        UserCognitiveProfile,
        UserTwinConsent,
    )
"""

import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# SQLite-compatible JSON for unit tests; JSONB voor productie
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class UserBehaviorObservation(Base):  # type: ignore[misc]
    """
    Geanonimiseerde gedragsobservatie van een user.

    Privacy: context en outcome_metrics worden door PrivacyFilter
    geanonimiseerd voordat ze hier worden opgeslagen.
    Retentie: expires_at veld voor automatische cleanup na 90 dagen.
    """

    __tablename__ = "user_behavior_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolatie -- FK naar tenants.id",
    )
    human_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Geanonimiseerde user identifier",
    )
    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    behavior_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="bijv. file_edit, rapid_switch, undo_loop",
    )
    # Geanonimiseerd door PrivacyFilter voor opslag
    context: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True, comment="Geanonimiseerde context data"
    )
    outcome_metrics: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True, comment="Geanonimiseerde metrics"
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Voor 90-dagen retention cleanup
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Automatisch cleanup na 90 dagen",
    )

    __table_args__ = (
        Index("idx_twin_obs_user_time", "human_user_id", "created_at"),
        Index("idx_twin_obs_session", "session_id", "created_at"),
        Index("idx_twin_obs_tenant_behavior", "tenant_id", "behavior_type"),
        Index("idx_twin_obs_expires", "expires_at"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<UserBehaviorObservation(id={self.id}, "
            f"user='{self.human_user_id}', "
            f"type='{self.behavior_type}')>"
        )


class UserCognitiveProfile(Base):  # type: ignore[misc]
    """
    Geleerd cognitief profiel van een user -- cumulatief bijgewerkt door
    de UserBehaviorObserver.

    Een profiel per user per tenant.
    """

    __tablename__ = "user_cognitive_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    human_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Geanonimiseerde user identifier",
    )
    coding_style: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True, comment="Geleerde coding stijl"
    )
    work_patterns: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True, comment="Werkpatronen (sessietijden, pauzes)"
    )
    blind_spots: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True, comment="Herhaalde foutpatronen"
    )
    strengths: Mapped[Any | None] = mapped_column(JSONType, nullable=True, comment="Sterke kanten")  # TODO(TYPE): replace Any with concrete type
    optimal_help_style: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="direct_code",
        server_default="direct_code",
        comment="bijv. direct_code, step_by_step, explain_first",
    )
    confidence_level: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )
    observation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    preferred_agents: Mapped[list[Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Focus Builder: agent IDs de gebruiker heeft geaccepteerd",
    )
    preferred_departments: Mapped[list[Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Focus Builder: departments van geaccepteerde agents",
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_aggregated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Watermark: tot wanneer observaties zijn verwerkt",
    )

    __table_args__ = (
        Index("idx_twin_profile_user", "human_user_id"),
        UniqueConstraint("tenant_id", "human_user_id", name="uq_twin_profile_tenant_user"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<UserCognitiveProfile(id={self.id}, "
            f"user='{self.human_user_id}', "
            f"confidence={self.confidence_level:.2f})>"
        )


class UserTwinConsent(Base):  # type: ignore[misc]
    """
    GDPR consent record per user.

    Artikel 7: Expliciete toestemming bijgehouden.
    Artikel 17: hard_delete_requested vlag voor Right to Erasure.
    Default: consent NIET gegeven (opt-in model, GDPR Art. 7).
    """

    __tablename__ = "user_twin_consent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    human_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    consent_given: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="Backward compat: AND of four categories. GDPR opt-in: default False.",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="disabled",
        server_default="'disabled'",
        comment="enabled | disabled | paused. Default disabled (GDPR opt-in).",
    )
    # Granular consent categories (added 2026-05-21, ADR-026 S.2)
    behavior_tracking: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="Allow behavior observations",
    )
    profile_aggregation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="Allow cognitive profile building",
    )
    ai_interventions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="Allow AI-generated suggestions",
    )
    cross_session_memory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="Allow profile to persist across sessions",
    )
    consent_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0",
        server_default="'1.0'",
        comment="Versie van de consent tekst",
    )
    # GDPR Artikel 17: Right to Erasure
    hard_delete_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="FALSE",
        comment="True = verwijder alle twin data voor deze user",
    )
    hard_delete_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Vrij veld voor audit trail"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "human_user_id", name="uq_twin_consent_tenant_user"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<UserTwinConsent(id={self.id}, "
            f"user='{self.human_user_id}', "
            f"consent={self.consent_given})>"
        )


class TwinSuggestionLog(Base):  # type: ignore[misc]
    """
    Per-suggestion cost tracking for fiscal audit compliance.

    Retention: 7 years (2555 days) per Dutch tax law (art. 52 AWR).
    Separate retention actor from user_behavior_observations (90 days).
    """

    __tablename__ = "twin_suggestion_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="e.g. Claude, Gemini, Local, Mock"
    )
    suggestion_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Generated suggestion (truncated if very long)"
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cost_eur: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=0.0,
        server_default="0",
        comment="Computed cost in EUR",
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    was_useful: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="User feedback: True=useful, False=not, None=no feedback"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Auto-cleanup after 7 years",
    )

    __table_args__ = (
        Index("idx_twin_suggestion_log_tenant_user", "tenant_id", "user_id"),
        Index("idx_twin_suggestion_log_expires", "expires_at"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<TwinSuggestionLog(id={self.id}, "
            f"provider='{self.provider_name}', "
            f"cost={self.cost_eur})>"
        )


class TenantLLMBudget(Base):  # type: ignore[misc]
    """
    Per-tenant monthly LLM budget cap.

    Soft cap: skip paid providers, use Ollama.
    Hard cap: skip all paid providers, use Mock only.
    """

    __tablename__ = "tenant_llm_budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False, comment="YYYY-MM format")
    budget_eur_soft: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=10.0,
        server_default="10.00",
    )
    budget_eur_hard: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=50.0,
        server_default="50.00",
    )
    spent_eur: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=0.0,
        server_default="0",
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "month", name="uq_tenant_llm_budget_month"),
        Index("idx_tenant_llm_budget_tenant", "tenant_id"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<TenantLLMBudget(tenant={self.tenant_id}, "
            f"month='{self.month}', "
            f"spent={self.spent_eur})>"
        )


class FocusBuilderAcceptedWorkflow(Base):  # type: ignore[misc]
    """Persisted proposals that the user has accepted. Used for recente workflows context."""

    __tablename__ = "focus_builder_accepted_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nodes: Mapped[Any] = mapped_column(JSONType, nullable=False, server_default="[]")  # TODO(TYPE): replace Any with concrete type
    edges: Mapped[Any] = mapped_column(JSONType, nullable=False, server_default="[]")  # TODO(TYPE): replace Any with concrete type
    intake_context: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_fb_accepted_user_tenant", "user_id", "tenant_id", "created_at"),
        {"extend_existing": True},
    )
