"""
Twin Events -- Dataclasses voor alle digital twin domain events.

Gebruik:
    event = UserBehaviorTracked(
        user_id="u1",
        tenant_id=1,
        behavior_type="file_edit",
        context={"edit_count": 3},
        trace_id="trace_001",
    )
    await event_bus.publish(event)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TwinEvent:
    """Base class voor alle digital twin events."""

    user_id: str
    tenant_id: int
    event_type: str = ""
    trace_id: str = ""
    timestamp: datetime = field(default_factory=_now)
    payload: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


@dataclass
class UserBehaviorTracked(TwinEvent):
    """Event: Een user gedrags-observatie is opgeslagen in de batch."""

    behavior_type: str = ""
    context: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        self.event_type = "twin.user_behavior.tracked"


@dataclass
class ProfileUpdated(TwinEvent):
    """Event: Cognitief profiel van een user is bijgewerkt."""

    profile_id: int | None = None
    confidence_level: float = 0.0
    observation_count: int = 0

    def __post_init__(self) -> None:
        self.event_type = "twin.profile.updated"


@dataclass
class InterventionSuggested(TwinEvent):
    """Event: De twin stelt een interventie voor aan de user."""

    intervention_type: str = ""  # "struggle", "reminder", "coach"
    message: str = ""
    confidence: float = 0.0

    def __post_init__(self) -> None:
        self.event_type = "twin.intervention.suggested"


@dataclass
class ConsentChanged(TwinEvent):
    """Event: User consent status is gewijzigd."""

    new_status: str = ""  # "enabled", "disabled", "paused"

    def __post_init__(self) -> None:
        self.event_type = "twin.consent.changed"


@dataclass
class HardDeleteRequested(TwinEvent):
    """Event: GDPR Right to Erasure verzoek ontvangen."""

    def __post_init__(self) -> None:
        self.event_type = "twin.hard_delete.requested"


@dataclass
class CritiqueScoreLow(TwinEvent):
    """Event: CriticAgent score onder Orient-fase drempel (SP-AGT-008)."""

    agent_name: str = ""
    score: float = 0.0

    def __post_init__(self) -> None:
        self.event_type = "twin.critique.score_low"
