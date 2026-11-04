"""
Memory Domain Schemas
=====================

Pydantic v2 request/response schemas for the digital twin memory API.

All schemas are tenant-safe by design:
- tenant_id is never accepted from client input (injected from JWT)
- status defaults to 'proposed' -- client cannot force 'accepted' without scope
- embedding vectors are excluded from API responses (internal use only)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ===========================================================================
# Shared enums (string literals -- avoids Pydantic/enum import issues)
# ===========================================================================

MEMORY_TYPES = [
    "semantic",
    "episodic",
    "procedural",
    "preference",
    "goal",
    "summary",
    "relationship",
]
MEMORY_STATUSES = ["proposed", "accepted", "contradicted", "archived"]
PRIVACY_SCOPES = ["private", "user", "workspace", "tenant"]
SOURCE_TYPES = ["chat", "tool", "import", "workflow", "consolidation", "manual"]
EVENT_TYPES = ["message", "tool_call", "decision", "error", "workflow_complete", "observation"]


# ===========================================================================
# AgentMemoryProfile schemas
# ===========================================================================


class GoalItem(BaseModel):
    """A single active goal entry."""

    id: str = Field(..., description="Unique goal identifier")
    title: str = Field(..., min_length=1, max_length=500)
    priority: int = Field(default=3, ge=1, le=9)
    description: str | None = None
    created_at: str | None = None

    model_config = {"extra": "ignore"}


class OperatingRule(BaseModel):
    """A single operating rule or constraint."""

    rule: str = Field(..., min_length=1, max_length=1000)
    source: str = Field(default="manual")  # manual|tenant_policy|agent_default
    added_at: str | None = None

    model_config = {"extra": "ignore"}


class DomainExpertise(BaseModel):
    """A topic the agent is expert in."""

    topic: str = Field(..., min_length=1, max_length=200)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    last_reinforced: str | None = None

    model_config = {"extra": "ignore"}


class AgentMemoryProfileCreate(BaseModel):
    """Create or upsert an agent memory profile."""

    agent_id: str = Field(..., min_length=1, max_length=100)
    agent_type: str | None = Field(None, max_length=50)
    persona_name: str | None = Field(None, max_length=200)
    persona_description: str | None = None
    active_goals: list[GoalItem] = Field(default_factory=list)
    operating_rules: list[OperatingRule] = Field(default_factory=list)
    domain_expertise: list[DomainExpertise] = Field(default_factory=list)
    owner_user_id: int | None = None

    model_config = {"extra": "ignore"}


class AgentMemoryProfileUpdate(BaseModel):
    """Partial update -- only provided fields are changed."""

    persona_name: str | None = Field(None, max_length=200)
    persona_description: str | None = None
    active_goals: list[GoalItem] | None = None
    operating_rules: list[OperatingRule] | None = None
    domain_expertise: list[DomainExpertise] | None = None

    model_config = {"extra": "ignore"}


class AgentMemoryProfileResponse(BaseModel):
    """Full profile response -- no embeddings, no internal fields."""

    id: int
    tenant_id: int
    agent_id: str
    agent_type: str | None
    persona_name: str | None
    persona_description: str | None
    active_goals: list[Any]  # TODO(TYPE): replace Any with concrete type
    operating_rules: list[Any]  # TODO(TYPE): replace Any with concrete type
    domain_expertise: list[Any]  # TODO(TYPE): replace Any with concrete type
    profile_version: int
    is_active: bool
    owner_user_id: int | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ===========================================================================
# MemoryItem schemas
# ===========================================================================


class MemoryItemWrite(BaseModel):
    """Write a single memory candidate."""

    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: str = Field(default="episodic")
    agent_id: str | None = Field(None, max_length=100)
    user_id: int | None = None
    workspace_id: int | None = None
    source_type: str = Field(default="chat")
    source_ref: str | None = Field(default=None, max_length=200)
    privacy_scope: str = Field(default="tenant")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    # status is ALWAYS 'proposed' on write -- cannot be set by client
    # auto_accept is controlled server-side by scope/source_type

    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        if v not in MEMORY_TYPES:
            raise ValueError(f"memory_type must be one of {MEMORY_TYPES}")
        return v

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
        return v

    @field_validator("privacy_scope")
    @classmethod
    def validate_privacy_scope(cls, v: str) -> str:
        if v not in PRIVACY_SCOPES:
            raise ValueError(f"privacy_scope must be one of {PRIVACY_SCOPES}")
        return v

    model_config = {"extra": "ignore"}


class MemoryItemBulkWrite(BaseModel):
    """Write multiple memory candidates in one request."""

    items: list[MemoryItemWrite] = Field(..., min_length=1, max_length=50)

    model_config = {"extra": "ignore"}


class MemoryItemResponse(BaseModel):
    """Public representation of a memory item -- no embedding vector."""

    id: int
    tenant_id: int
    agent_id: str | None
    user_id: int | None
    workspace_id: int | None
    memory_type: str
    content: str
    confidence: float
    importance: float
    source_type: str
    source_ref: str | None
    privacy_scope: str
    status: str
    valid_from: datetime
    valid_to: datetime | None
    tags: list[Any]  # TODO(TYPE): replace Any with concrete type
    entities: list[Any]  # TODO(TYPE): replace Any with concrete type
    provenance: list[Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class MemoryItemStatusUpdate(BaseModel):
    """Accept or archive a memory item."""

    status: str = Field(...)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = ["accepted", "archived", "contradicted"]
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v

    model_config = {"extra": "ignore"}


# ===========================================================================
# Memory Query schemas
# ===========================================================================


class MemoryQueryRequest(BaseModel):
    """Hybrid retrieval query."""

    query: str = Field(..., min_length=1, max_length=2000)
    agent_id: str | None = Field(None, max_length=100)
    memory_types: list[str] | None = None
    privacy_scope: str = Field(default="tenant")
    status_filter: str = Field(default="accepted")
    top_k: int = Field(default=15, ge=1, le=50)
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)

    model_config = {"extra": "ignore"}


class MemoryQueryResponse(BaseModel):
    """Retrieval results with trace info."""

    items: list[MemoryItemResponse]
    total_candidates: int
    query_time_ms: float
    retrieval_method: str  # "vector"|"fulltext"|"hybrid"

    model_config = {"from_attributes": True}


# ===========================================================================
# Boot context schemas
# ===========================================================================


class BootContextRequest(BaseModel):
    """Request a packed boot context for an agent session."""

    agent_id: str = Field(..., min_length=1, max_length=100)
    session_id: int | None = None
    token_budget: int = Field(default=2000, ge=200, le=8000)

    model_config = {"extra": "ignore"}


class BootContextResponse(BaseModel):
    """Structured boot context injected at session start."""

    agent_id: str
    tenant_id: int
    profile: AgentMemoryProfileResponse | None
    active_goals: list[Any]  # TODO(TYPE): replace Any with concrete type
    recent_episodes: list[MemoryItemResponse]
    top_facts: list[MemoryItemResponse]
    top_preferences: list[MemoryItemResponse]
    estimated_tokens: int
    built_at: datetime

    model_config = {"from_attributes": True}


# ===========================================================================
# SessionMemoryEvent schemas
# ===========================================================================


class SessionEventWrite(BaseModel):
    """Log a session event to the append-only event stream."""

    session_id: int
    agent_id: str = Field(..., min_length=1, max_length=100)
    user_id: int | None = None
    event_type: str = Field(default="message")
    event_data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    memory_candidate: bool = Field(default=False)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"event_type must be one of {EVENT_TYPES}")
        return v

    model_config = {"extra": "ignore"}


class SessionEventResponse(BaseModel):
    id: int
    tenant_id: int
    session_id: int
    agent_id: str
    event_type: str
    memory_candidate: bool
    resolved_item_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===========================================================================
# ConsolidationRun schemas
# ===========================================================================


class ConsolidationRunResponse(BaseModel):
    id: int
    tenant_id: int
    agent_id: str | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    sessions_processed: int
    events_processed: int
    items_created: int
    items_archived: int
    contradictions_found: int
    error_message: str | None

    model_config = {"from_attributes": True}


# ===========================================================================
# Stats / health
# ===========================================================================


class MemoryStatsResponse(BaseModel):
    """Aggregate stats for a tenant's memory layer."""

    tenant_id: int
    total_items: int
    accepted_items: int
    proposed_items: int
    archived_items: int
    by_type: dict[str, int]
    by_agent: dict[str, int]
    last_consolidation: datetime | None
    last_write: datetime | None
