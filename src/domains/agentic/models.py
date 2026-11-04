"""
Agentic Domain Models - TDD Implementation with Cross-Domain Relationships

Uses UNIDIRECTIONAL relationships for cross-domain access (Feature->Tenant, UserPersona->User).
Uses BIDIRECTIONAL relationships within the agentic domain (AgentSession<->SessionMessage).

Run tests: pytest tests/unit/agentic/ -v
"""

from datetime import datetime
from typing import Optional

# Use plain JSON type for SQLite compatibility in tests
# JSONB is PostgreSQL-specific and causes errors with SQLite
from sqlalchemy import JSON as JSONType
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# Import Base from canonical location
from src.core.database.database import Base

# =============================================================================
# PromptTemplate Model (Moved up to resolve dependency in Feature)
# =============================================================================


class PromptTemplate(Base):  # type: ignore[misc]
    """Versioned prompt template for LLM interactions."""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)

    # Template content
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_format: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Localization
    supported_locales: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    localized_variants: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), server_default="draft", nullable=False)

    # Foreign keys
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Unidirectional relationships
    tenant = relationship("Tenant")
    creator = relationship("User", foreign_keys=[created_by])
    updated_at = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("name", "version", "tenant_id", name="uq_prompt_template_version"),
        Index("ix_prompt_templates_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<PromptTemplate(name={self.name}, version={self.version})>"


# =============================================================================
# Feature Model
# =============================================================================


class Feature(Base):  # type: ignore[misc]
    """
    Platform feature definition.
    Features represent capabilities like 'workflow', 'data_analysis', etc.
    """

    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    # Feature configuration
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    keywords: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    example_queries: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    capabilities: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Intent detection (used by feature_registry.py)
    intent_keywords: Mapped[object | None] = mapped_column(
        JSONType, nullable=True
    )  # {locale: [keywords]}
    route_patterns: Mapped[object | None] = mapped_column(
        JSONType, nullable=True
    )  # ["/path/*", ...]
    domain_context = mapped_column(String(100), nullable=True)  # e.g., "workflows", "analytics"

    # Foreign keys
    prompt_template_id = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Unidirectional relationships (NO back_populates to avoid circular imports)
    tenant = relationship("Tenant")
    prompt_template = relationship("PromptTemplate")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_features_tenant_active", "tenant_id", "is_active"),
        Index("ix_features_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Feature(id={self.id}, name={self.name})>"


# =============================================================================
# ToolDefinition Model
# =============================================================================


class ToolDefinition(Base):  # type: ignore[misc]
    """Tool/function definitions for LLM function calling."""

    __tablename__ = "tool_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    # OpenAI-compatible function schema
    function_schema: Mapped[object] = mapped_column(JSONType, nullable=False)

    # Implementation details
    implementation_type: Mapped[str] = mapped_column(
        String(50), server_default="internal", nullable=False
    )
    implementation_config: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Access control
    required_permissions: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_tool_definitions_category", "category"),
        Index("ix_tool_definitions_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ToolDefinition(name={self.name})>"


# =============================================================================
# PromptMetrics Model
# =============================================================================


class PromptMetrics(Base):  # type: ignore[misc]
    """Metrics for prompt template performance tracking."""

    __tablename__ = "prompt_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Metrics
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    user_feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<PromptMetrics(session={self.session_id})>"


# =============================================================================
# UserPersona Model
# =============================================================================


class UserPersona(Base):  # type: ignore[misc]
    """User personalization profile for adaptive responses."""

    __tablename__ = "user_personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Persona type (explorer, builder, analyst, etc.)
    persona_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Preferences
    expertise_level: Mapped[int] = mapped_column(Integer, server_default="5", nullable=False)
    prefers_structured_output: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    prefers_concise_responses: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    preferences: Mapped[object | None] = mapped_column(
        JSONType, nullable=True
    )  # Generic preferences dict

    # Learned patterns
    common_topics: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    common_mistakes: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    preferred_tools: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Stats
    total_interactions: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    avg_satisfaction: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Unidirectional relationships (NO back_populates!)
    user = relationship("User")
    tenant = relationship("Tenant")

    def __repr__(self) -> str:
        return f"<UserPersona(user_id={self.user_id})>"


# =============================================================================
# AgentSession Model
# =============================================================================


class AgentSession(Base):  # type: ignore[misc]
    """Session metadata for conversational continuity."""

    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session state
    session_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g., 'chat', 'workflow'
    current_feature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    extra_metadata: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Unidirectional relationships to RBAC domain
    user = relationship("User")
    tenant = relationship("Tenant")

    # Bidirectional relationship WITHIN agentic domain - OK!
    messages = relationship(
        "SessionMessage", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AgentSession(id={self.id})>"


# =============================================================================
# SessionMessage Model
# =============================================================================


class SessionMessage(Base):  # type: ignore[misc]
    """Individual message within an agent session."""

    __tablename__ = "session_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id = mapped_column(
        String(100),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional metadata
    detected_feature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tools_used: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    extra_metadata: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Bidirectional relationship to AgentSession (within same domain - OK!)
    session = relationship("AgentSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<SessionMessage(id={self.id}, role={self.role})>"


# =============================================================================
# Module exports
# =============================================================================

# =============================================================================
# Prompt Experiment Models (Phase 6)
# =============================================================================


class PromptExperiment(Base):  # type: ignore[misc]
    """Metadata for A/B experiments on prompts."""

    __tablename__ = "prompt_experiments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # Maps to ABTest.test_id
    # ADR-005: tenant_id NOT NULL (DATA-001/DB-AUDIT-001, AUDIT-ARCH-2026-07-02 Groep 4)
    tenant_id = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt_template_id = mapped_column(Integer, ForeignKey("prompt_templates.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    variants = relationship(
        "PromptExperimentVariant",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    template = relationship("PromptTemplate")

    def __repr__(self) -> str:
        return f"<PromptExperiment(id={self.id}, name={self.name})>"


class PromptExperimentVariant(Base):  # type: ignore[misc]
    """Specific variant content for an experiment."""

    __tablename__ = "prompt_experiment_variants"

    # Composite PK: experiment_id + variant_id
    experiment_id = mapped_column(
        String(50),
        ForeignKey("prompt_experiments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    variant_id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # e.g., "Control", "Variant_A"

    content: Mapped[str] = mapped_column(Text, nullable=False)  # The prompt text
    is_control: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    traffic_allocation: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationship
    experiment = relationship("PromptExperiment", back_populates="variants")

    def __repr__(self) -> str:
        return f"<PromptExperimentVariant({self.experiment_id}, {self.variant_id})>"


# =============================================================================
# Module exports
# =============================================================================

__all__ = [
    "Feature",
    "PromptTemplate",
    "ToolDefinition",
    "PromptMetrics",
    "UserPersona",
    "AgentSession",
    "SessionMessage",
    "PromptExperiment",
    "PromptExperimentVariant",
]
