"""
Core data types for the Agent Council.

All types are frozen dataclasses (immutable) so that they can be safely
shared across asyncio tasks and serialized into the hash chain without
fear of mutation between read and write.

Per CLAUDE.md regel 3: all datetimes are timezone-aware UTC.
Per CLAUDE.md regel 10: all source code is ASCII-only (Dutch in comments OK).

See docs/copilot-architecture.md section 5 and docs/adr/027-copilot-agent-council.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from src.core.copilot.council.policies.models import CouncilPolicy


# Re-exports: VerdictType and OfficerVerdict moved to governance.models (SP-DSM-005, ADR-027).
# copilot -> governance is ADR-027 by design. These re-exports preserve backward compat.
from src.core.governance.models import OfficerVerdict as OfficerVerdict
from src.core.governance.models import VerdictType as VerdictType


# ----------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------


class DecisionVerdict(str, Enum):
    """Final aggregated Council verdict on a proposal."""

    APPROVED = "approved"
    MODIFIED = "modified"
    HITL_REQUIRED = "hitl_required"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class Severity(str, Enum):
    """Severity for proactive signals and notifications."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"  # Bypasses notification budget


class DataClassification(str, Enum):
    """Data sensitivity class per ADR-019."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # PII, financials, health


class ProposalTrigger(str, Enum):
    """What initiated the proposal."""

    USER_REQUEST = "user_request"  # Cmd+K, chat, focus-builder
    PROACTIVE_MONITOR = "proactive_monitor"  # Background scanner
    DIGITAL_TWIN_SUGGESTION = "twin_suggestion"
    SCHEDULED = "scheduled"  # Recurring task
    ESCALATION = "escalation"  # From another agent


# ----------------------------------------------------------------------------
# Core data types
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    """
    A proposed Co-Pilot action that the Council must adjudicate.

    Always constructed by the CopilotService; never accepted from external
    callers. tenant_id and user_id come from the JWT (CLAUDE.md regel 6 +
    ADR-003), never from request body.
    """

    tenant_id: int
    user_id: int
    trigger: ProposalTrigger
    action_type: str  # e.g. "send_notification", "navigate_to"
    action_params: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    reasoning: str  # Natural language: why is this proposed?
    data_classification: DataClassification
    confidence: float  # 0.0-1.0, LLM-confidence
    model_id: str  # e.g. "deepseek-chat-v3.1"
    model_version: str  # For reproducibility
    context_snapshot: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ]  # Route, page, recent actions, twin profile  # TODO(TYPE): replace Any with concrete type
    message: str = ""  # Final natural language text for the user
    proposal_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    capabilities: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # Platform capability snapshot  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        if self.tenant_id <= 0:
            raise ValueError("tenant_id must be > 0")
        if self.user_id <= 0:
            raise ValueError("user_id must be > 0")
        # Validation: confidence must be in [0, 1]
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        # Validation: timestamp must be timezone-aware (CLAUDE.md regel 3)
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")


@dataclass(frozen=True)
class CouncilDecision:
    """
    Final aggregated decision by the Council.

    Carries the full deliberation result for persistence in the hash chain
    and for the right-to-explanation API.
    """

    proposal_id: UUID
    tenant_id: int
    user_id: int
    verdict: DecisionVerdict
    officer_verdicts: tuple[OfficerVerdict, ...]  # All 7 Officer verdicts
    explanation_for_user: str  # GDPR art. 13-15 right-to-explanation
    decision_hash: str  # SHA-256 chained hash
    previous_decision_hash: str | None  # None for first decision per tenant
    deliberation_ms: int
    modifications: dict[str, Any] | None = (  # TODO(TYPE): replace Any with concrete type
        None  # For DecisionVerdict.MODIFIED  # TODO(TYPE): replace Any with concrete type
    )
    hitl_request_id: UUID | None = None  # For DecisionVerdict.HITL_REQUIRED
    decision_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.tenant_id <= 0:
            raise ValueError("tenant_id must be > 0")
        if self.user_id <= 0:
            raise ValueError("user_id must be > 0")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")


@dataclass(frozen=True)
class DeliberationContext:
    """
    Context passed to each Officer during deliberation.

    Officers may read from this but never mutate; mutations would compromise
    the parallel deliberation invariant.
    """

    tenant_settings: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ]  # Per-tenant policy overrides  # TODO(TYPE): replace Any with concrete type
    user_preferences: dict[
        str, Any
    ]  # Notification budget, etc.  # TODO(TYPE): replace Any with concrete type
    twin_profile: (
        dict[str, Any] | None
    )  # Digital Twin user profile (with consent)  # TODO(TYPE): replace Any with concrete type
    recent_decisions: tuple[CouncilDecision, ...]  # Last N decisions for this user
    deadline_ms: int  # Hard deadline for total deliberation
    request_id: UUID  # Trace correlation
    policy: Optional["CouncilPolicy"] = None  # The effective CouncilPolicy for this turn
    # CRITICAL-4: platform capability metadata
    registered_tools: list[dict[str, Any]] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list
    )  # TODO(TYPE): replace Any with concrete type
    agent_health: dict[str, str] = field(default_factory=dict)
    domain_packs: list[str] = field(default_factory=list)
