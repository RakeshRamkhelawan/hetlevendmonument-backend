"""
Agent Models - Domain models for agent registry system
Migrated from core.database.models (Phase 6 Task 6, Phase 7)

Usage:
    from src.core.agents.models import RegisteredAgent, Agent
"""

import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use SQLite-compatible JSON type for testing, PostgreSQL JSONB for production
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB
# Agent metadata columns MUST use JSONB even in testing (migration expects JSONB)
AgentJSONType = JSONB


class RegisteredAgent(Base):  # type: ignore[misc]
    """
    RegisteredAgent model voor FASE 6 agent registry persistentie
    Zoals gespecificeerd in STAP 6.1.1: velden voor agent_id, address, capabilities (JSONB), en last_heartbeat
    Enhanced with TAAK 3.2 performance indexes for agent registry queries

    MIGRATED from core.database.models (Phase 6 Task 6)
    UPDATED: Added tenant_id for automatic tenant isolation (Phase 7)
    """

    __tablename__ = "registered_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # NEW: Agent name
    description: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )  # NEW: Agent description
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    capabilities: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=False, server_default="specialist", index=True
    )
    capabilities_tags: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        AgentJSONType, nullable=True, default=list
    )
    required_agents: Mapped[Any | None] = mapped_column(AgentJSONType, nullable=True, default=list)  # TODO(TYPE): replace Any with concrete type
    tier: Mapped[str | None] = mapped_column(
        String(50), nullable=False, server_default="professional", index=True
    )
    health_status: Mapped[str | None] = mapped_column(
        String(50), nullable=False, server_default="unknown", index=True
    )
    version: Mapped[str | None] = mapped_column(String(50), nullable=False, server_default="1.0")
    owner_team: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_metadata: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        "metadata", AgentJSONType, nullable=True, default=dict
    )

    # Performance indexes for agent registry queries
    __table_args__ = (
        # Per-tenant unique constraint: each tenant can have its own agent_id
        UniqueConstraint("agent_id", "tenant_id", name="uq_registered_agent_per_tenant"),
        # Index for fast lookups by agent_id alone (cross-tenant)
        Index("idx_registered_agent_id", "agent_id"),
        # Index for active agent queries (heartbeat-based)
        Index("idx_agent_heartbeat", "last_heartbeat"),
        # Index for agent health monitoring
        Index("idx_agent_status", "last_heartbeat", "created_at"),
        # Index for tenant isolation queries
        Index("idx_agent_tenant", "tenant_id", "agent_id"),
        # Indexes for Phase 0a unified agent fields (migration 20260506)
        Index("idx_agent_category", "category"),
        Index("idx_agent_health", "health_status"),
        Index("idx_agent_tier", "tier"),
        Index("idx_agent_team", "owner_team"),
        {"extend_existing": True},  # Allow redefinition if already exists
    )

    def __repr__(self) -> str:
        return f"<RegisteredAgent(id={self.id}, agent_id='{self.agent_id}', address='{self.address}', tenant_id={self.tenant_id})>"


class Agent(Base):  # type: ignore[misc]
    """
    Agent model - stub for basic agent data
    Migrated from core.database.models in Phase 7.
    SECURITY FIX (P5.1.4): Changed tenant_id to nullable=False for RLS
    """

    __tablename__ = "agents"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # SECURITY FIX (P5.1.4): Changed from nullable=True to nullable=False for proper RLS
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Task 3: Add department_id foreign key for template enrichment
    department_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name='{self.name}', type='{self.agent_type}')>"
