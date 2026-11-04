"""
Memory Domain Models
====================

SQLAlchemy ORM models for the Digital Twin persistent memory layer.

Sprint A tables (4 core tables):
- agent_memory_profiles: agent identity, goals, operating rules
- memory_items:          durable memory (facts, episodes, preferences, summaries)
- session_memory_events: append-only event log per session
- memory_consolidation_runs: nightly batch job tracking

Design rules:
- All tables have tenant_id (Integer FK -> tenants.id) -- NEVER missing
- Soft-delete via deleted_at timestamp
- status=proposed is the safe default for all MemoryItems
- auto_accept=True only for trusted system-generated items
"""

import os
from datetime import datetime
from typing import Any, Optional, Set

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# ---------------------------------------------------------------------------
# Try to import pgvector for semantic search.
# Falls back to Text (stored as JSON string) if extension not available.
# ---------------------------------------------------------------------------
try:
    from pgvector.sqlalchemy import Vector as _PGVector

    def _vector_column(dims: int) -> Column[Any]:  # TODO(TYPE): replace Any with concrete type
        """Create a pgvector column with configurable dimensions."""
        return Column(_PGVector(dims), nullable=True)

    PGVECTOR_AVAILABLE = True
except ImportError:

    def _vector_column(dims: int) -> Column[Any]:  # TODO(TYPE): replace Any with concrete type
        """Fallback: store embedding as JSON text when pgvector not installed."""
        _ = dims  # unused in fallback
        return Column(Text, nullable=True)

    PGVECTOR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configurable embedding dimensions -- set MEMORY_EMBEDDING_DIMS in .env
# Default 1536 = OpenAI text-embedding-3-small / text-embedding-ada-002
# Set 768 for nomic-embed-text (Ollama local), 3072 for text-embedding-3-large
# ---------------------------------------------------------------------------
EMBEDDING_DIMS: int = int(os.getenv("MEMORY_EMBEDDING_DIMS", "1536"))


# ===========================================================================
# Model 1: AgentMemoryProfile
# ===========================================================================


class AgentMemoryProfile(Base):  # type: ignore[misc]
    """
    Per-agent, per-tenant identity profile.

    Stores who the agent is, what it's working on, and its operating rules.
    This is injected at session boot via ContextPackerService.

    Versioned via 'profile_version' so changes can be diffed/audited.
    """

    __tablename__ = "agent_memory_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Multi-tenant isolation -- mandatory
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Agent identification
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # CVA, ORCHESTRATOR, etc.
    persona_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    persona_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Owner (optional -- some agents are tenant-wide, not user-specific)
    owner_user_id = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Living state -- stored as JSON for flexibility, versioned for audit
    active_goals: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [{"id": "g1", "title": "...", "priority": 1, "created_at": "..."}]

    operating_rules: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [{"rule": "Always cite sources", "source": "tenant_policy", "added_at": "..."}]

    domain_expertise: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [{"topic": "GDPR compliance", "confidence": 0.9, "last_reinforced": "..."}]

    # Version counter -- increment on every meaningful update
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Active flag -- soft deactivate without deleting
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One active profile per agent per tenant (enforced in service layer too)
        Index("idx_amp_tenant_agent", "tenant_id", "agent_id"),
        Index("idx_amp_tenant_agent_active", "tenant_id", "agent_id", "is_active"),
        Index("idx_amp_owner", "tenant_id", "owner_user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentMemoryProfile(id={self.id}, tenant_id={self.tenant_id}, "
            f"agent_id='{self.agent_id}', version={self.profile_version})>"
        )


# ===========================================================================
# Model 2: MemoryItem
# ===========================================================================


class MemoryItem(Base):  # type: ignore[misc]
    """
    Durable memory unit -- the core building block of the digital twin.

    Every piece of persistent knowledge the agent accumulates is a MemoryItem.

    Memory types:
      semantic     -- stable facts ("Tenant uses EU GDPR data residency")
      episodic     -- specific events ("On 2026-03-01 completed workflow X")
      procedural   -- how-to knowledge ("Use OAuth2 for external API calls")
      preference   -- user/tenant preferences ("Prefers concise summaries")
      goal         -- current objective ("Finish Q2 compliance audit")
      summary      -- consolidation product ("Week 10 summary for project A")
      relationship -- entity-entity facts ("User A is manager of team B")

    Status lifecycle:
      proposed  -> item needs review (default -- SAFE)
      accepted  -> confirmed true, used in retrieval
      contradicted -> conflicts with another accepted item, flagged
      archived  -> retired, kept for audit trail

    Security:
      privacy_scope controls cross-agent/cross-user visibility.
      NEVER return items where tenant_id != current_tenant_id.
    """

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Multi-tenant isolation -- NEVER query without this
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Scope -- agent-specific, user-specific, or workspace-wide
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    user_id = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )  # future: FK to workspaces

    # Memory classification
    memory_type = mapped_column(
        String(20),
        nullable=False,
        index=True,
        # Values: semantic|episodic|procedural|preference|goal|summary|relationship
    )

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_embedding = _vector_column(EMBEDDING_DIMS)

    # Quality signals
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)  # 0.0-1.0
    importance: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False
    )  # 0.0-1.0, decays over time

    # Provenance
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Values: chat|tool|import|workflow|consolidation|manual
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # FK-like ref: conversation_id, workflow_execution_id, etc.

    # Visibility
    privacy_scope = mapped_column(
        String(20),
        default="tenant",
        nullable=False,
        index=True,
        # Values: private|user|workspace|tenant
    )

    # Lifecycle
    status = mapped_column(
        String(20),
        default="proposed",
        nullable=False,
        index=True,
        # Values: proposed|accepted|contradicted|archived
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # None = permanent

    # Enrichment (set by worker after initial write)
    tags: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # ["project:compliance", "topic:GDPR", "quarter:Q2-2026"]
    entities: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [{"type": "person", "value": "Alice"}, {"type": "org", "value": "Acme"}]
    provenance: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [{"source": "chat", "ref": "conv_123", "extracted_at": "..."}]

    # Dedup tracking
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # SHA-256 of normalised content for exact-duplicate detection

    # Contradiction tracking
    contradicts_item_id = mapped_column(
        Integer,
        ForeignKey("memory_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Core retrieval indexes
        Index("idx_mi_tenant_agent_type_status", "tenant_id", "agent_id", "memory_type", "status"),
        Index("idx_mi_tenant_status_scope", "tenant_id", "status", "privacy_scope"),
        Index("idx_mi_tenant_agent_created", "tenant_id", "agent_id", "created_at"),
        Index("idx_mi_dedup_hash", "tenant_id", "dedup_hash"),
        Index("idx_mi_source", "tenant_id", "source_type", "source_ref"),
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryItem(id={self.id}, tenant_id={self.tenant_id}, "
            f"type='{self.memory_type}', status='{self.status}')>"
        )


# ===========================================================================
# Model 3: SessionMemoryEvent
# ===========================================================================


class SessionMemoryEvent(Base):  # type: ignore[misc]
    """
    Append-only event log for a single agent session.

    Every meaningful moment in a session -- message, tool call, decision,
    error -- is recorded here before being promoted to a durable MemoryItem.

    This is the raw feed. ConsolidationWorker processes it nightly.

    Rules:
    - NEVER update or delete rows -- this is an audit log
    - memory_candidate=True flags events that should become MemoryItems
    - resolved_item_id is set once the event has been promoted
    """

    __tablename__ = "session_memory_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Multi-tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session reference -- FK to agentic_sessions (already exists)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Event classification
    event_type = mapped_column(
        String(50),
        nullable=False,
        index=True,
        # Values: message|tool_call|decision|error|workflow_complete|observation
    )
    event_data: Mapped[Any] = mapped_column(JSON, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # Raw event payload -- content varies by event_type

    # Memory pipeline flags
    memory_candidate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    # True = this event is interesting enough to promote to MemoryItem

    resolved_item_id = mapped_column(
        Integer,
        ForeignKey("memory_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set once this event has been promoted to a MemoryItem

    # Append-only timestamp -- NO updated_at
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_sme_tenant_session", "tenant_id", "session_id"),
        Index("idx_sme_tenant_agent_created", "tenant_id", "agent_id", "created_at"),
        Index("idx_sme_tenant_candidates", "tenant_id", "memory_candidate", "resolved_item_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SessionMemoryEvent(id={self.id}, session_id={self.session_id}, "
            f"event_type='{self.event_type}', candidate={self.memory_candidate})>"
        )


# ===========================================================================
# Model 4: MemoryConsolidationRun
# ===========================================================================


class MemoryConsolidationRun(Base):  # type: ignore[misc]
    """
    Tracks nightly consolidation job executions per tenant.

    One row per run. Used for monitoring, debugging, and rollback decisions.
    Part of the observability loop -- linked to Prometheus metrics in Sprint C.
    """

    __tablename__ = "memory_consolidation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Scope -- None means full tenant consolidation
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Execution window
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status = mapped_column(
        String(20),
        default="running",
        nullable=False,
        index=True,
        # Values: running|completed|failed|partial
    )

    # Outcome metrics
    sessions_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_archived: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contradictions_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # {"model_used": "gpt-4o-mini", "token_cost": 1240, "p95_latency_ms": 342}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_mcr_tenant_status", "tenant_id", "status"),
        Index("idx_mcr_tenant_started", "tenant_id", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryConsolidationRun(id={self.id}, tenant_id={self.tenant_id}, "
            f"status='{self.status}', items_created={self.items_created})>"
        )


# ===========================================================================
# Model 5: MemoryRetrievalTrace  (advised: needed for evals)
# ===========================================================================


class MemoryRetrievalTrace(Base):  # type: ignore[misc]
    """
    Trace log for every retrieval query.

    Records what was queried, what came back, and why -- enabling:
    - "Why did the agent know this?" post-hoc analysis
    - Recall quality metrics (hit rate, miss rate, relevance scoring)
    - Regression testing for retrieval changes
    - GDPR audit: what was the agent shown before a decision

    Append-only. Never update rows.
    """

    __tablename__ = "memory_retrieval_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # The query that was executed
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # estimated query tokens

    # What came back
    result_item_ids: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # [item_id, item_id, ...] -- ordered by rank
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # How it was retrieved
    retrieval_method: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # vector|fulltext|hybrid
    top_k_requested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # For future relevance scoring (Sprint C eval framework)
    relevance_scores: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # TODO(TYPE): replace Any with concrete type
    # [{"item_id": 1, "score": 0.87}, ...]

    # Append-only timestamp
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_mrt_tenant_agent", "tenant_id", "agent_id"),
        Index("idx_mrt_tenant_session", "tenant_id", "session_id"),
        Index("idx_mrt_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryRetrievalTrace(id={self.id}, tenant_id={self.tenant_id}, "
            f"method='{self.retrieval_method}', results={self.result_count})>"
        )


# ===========================================================================
# Model 6: AgentProfileSnapshot  (advised: versioned snapshots for diffing)
# ===========================================================================


class AgentProfileSnapshot(Base):  # type: ignore[misc]
    """
    Immutable point-in-time snapshot of an AgentMemoryProfile.

    Created automatically every time upsert_profile() runs.
    Enables:
    - Diff between profile_version N and N+1
    - Rollback to a previous profile state
    - Audit trail: who changed what, when
    - GDPR: "what did the agent believe at time T"

    Append-only. Never update or delete rows.
    """

    __tablename__ = "agent_profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    profile_id = mapped_column(
        Integer,
        ForeignKey("agent_memory_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # The version this snapshot captures
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full state at this version -- JSON snapshot of all mutable fields
    snapshot: Mapped[Any] = mapped_column(JSON, nullable=False)  # TODO(TYPE): replace Any with concrete type
    # {
    #   "active_goals": [...],
    #   "operating_rules": [...],
    #   "domain_expertise": [...],
    #   "persona_name": "...",
    #   "persona_description": "..."
    # }

    # Who triggered this change
    changed_by_user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # "manual_update"|"consolidation"|"import"|"auto_goal_update"

    # Append-only timestamp
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_aps_profile_version", "profile_id", "profile_version"),
        Index("idx_aps_tenant_agent", "tenant_id", "agent_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentProfileSnapshot(id={self.id}, profile_id={self.profile_id}, "
            f"version={self.profile_version})>"
        )
