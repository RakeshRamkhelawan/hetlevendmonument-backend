"""
Conversation Models - Domain models for CVA conversations and user sessions

Migrated from core.database.models in Phase 7.
These are the authoritative models for conversation-related data.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use SQLite-compatible JSON type for testing, PostgreSQL JSONB for production
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class Conversation(Base):  # type: ignore[misc]
    """Extended Conversation model for CVA Agent (Phase 2)

    SECURITY FIX (P5.1.4): Changed tenant_id to nullable=False for RLS
    PHASE 2 (2026-02-06): Added user_id, agent_id, is_active, updated_at fields
    """

    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conversations_tenant_user", "tenant_id", "user_id"),
        Index("idx_conversations_updated_at", "updated_at"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # SECURITY FIX (P5.1.4): Changed from nullable=True to nullable=False for proper RLS
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PHASE 2: Additional fields for CVA Agent
    user_id = mapped_column(
        Integer, nullable=True, index=True
    )  # FK to users (nullable for backwards compat)
    agent_id = mapped_column(String(100), nullable=True, default="cva")  # Which agent handled this
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)  # Soft delete support
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )  # Track last message time

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class ConversationMessage(Base):  # type: ignore[misc]
    """Individual messages in a conversation (Phase 2)

    Stores user/assistant messages for chat history.
    Each message is a separate row for flexible querying.

    NEO AUDIT FIX (P0): Added tenant_id for proper multi-tenant isolation
    """

    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("idx_messages_conversation_timestamp", "conversation_id", "timestamp"),
        Index("idx_messages_tenant_id", "tenant_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user", "assistant", "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Token count for this message
    model: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # Which LLM model was used
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage(id={self.id}, role='{self.role}', conversation_id={self.conversation_id})>"


class CVAConversation(Base):  # type: ignore[misc]
    """CVA conversation history for persistent chat sessions"""

    __tablename__ = "cva_conversations"
    __table_args__ = (
        Index("ix_cva_session_id", "session_id"),
        Index("ix_cva_user_id", "user_id"),
        Index("ix_cva_created_at", "created_at"),
        Index("ix_cva_topic", "conversation_topic"),
        Index("ix_cva_turn", "conversation_turn"),
        Index("ix_cva_tenant_id", "tenant_id"),
        {"extend_existing": True},
    )

    id = mapped_column(String(50), primary_key=True, default=lambda: f"conv_{uuid.uuid4().hex[:8]}")
    session_id: Mapped[str] = mapped_column(String(50), nullable=False)  # Links to UserSession
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    # SECURITY FIX (P5.1.4): Changed from nullable=True to nullable=False for proper RLS
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )  # Multi-tenant support

    # Conversation content
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    cva_response: Mapped[str] = mapped_column(Text, nullable=False)

    # Response metadata
    response_metadata: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, default=dict
    )  # provider, model, tokens, etc.
    performance_data: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, default=dict
    )  # execution_time, cost, etc.

    # Context tracking
    conversation_turn: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3, etc.
    context_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Summary of conversation so far

    # Learning data
    user_feedback: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # positive, negative, neutral
    feedback_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File attachments
    attached_files: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, default=list
    )  # List of file paths/metadata

    # Classification
    conversation_topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conversation_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    keywords: Mapped[Any | None] = mapped_column(JSONType, default=list)  # TODO(TYPE): replace Any with concrete type

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )


class UserSession(Base):  # type: ignore[misc]
    """User sessions for the Mission Control interface"""

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_session_token", "session_token"),
        Index("ix_session_user", "user_id"),
        Index("ix_session_activity", "last_activity"),
        Index("ix_session_expires", "expires_at"),
        Index("ix_session_tenant_id", "tenant_id"),
        {"extend_existing": True},
    )

    id = mapped_column(
        String(50), primary_key=True, default=lambda: f"session_{uuid.uuid4().hex[:8]}"
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    session_token: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    # SECURITY FIX (P5.1.4): Changed from nullable=True to nullable=False for proper RLS
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )  # Multi-tenant support

    # Session data
    session_data: Mapped[Any | None] = mapped_column(JSONType, default=dict)  # TODO(TYPE): replace Any with concrete type
    user_preferences: Mapped[Any | None] = mapped_column(JSONType, default=dict)  # TODO(TYPE): replace Any with concrete type

    # Activity tracking
    last_activity: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    page_views: Mapped[int | None] = mapped_column(Integer, default=0)
    actions_count: Mapped[int | None] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Client info
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
