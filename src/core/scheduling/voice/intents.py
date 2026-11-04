"""
Voice intent definitions for scheduling voice interface.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class VoiceIntentType(Enum):
    """Supported voice intents for scheduling."""

    # Meeting management
    SCHEDULE_MEETING = "schedule_meeting"
    RESCHEDULE_MEETING = "reschedule_meeting"
    CANCEL_MEETING = "cancel_meeting"

    # Queries
    CHECK_AVAILABILITY = "check_availability"
    LIST_MEETINGS = "list_meetings"
    GET_MEETING_DETAILS = "get_meeting_details"

    # Actions
    SUGGEST_TIMES = "suggest_times"
    BLOCK_FOCUS_TIME = "block_focus_time"
    ADD_ATTENDEE = "add_attendee"
    REMOVE_ATTENDEE = "remove_attendee"

    # Clarification
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


@dataclass
class VoiceIntent:
    """Parsed intent from voice input."""

    intent_type: VoiceIntentType
    confidence: float  # 0.0 - 1.0

    # Extracted entities
    participants: list[str] = field(default_factory=list)
    date_expression: str | None = None  # "tomorrow", "next week", "January 15th"
    time_expression: str | None = None  # "3pm", "morning", "after lunch"
    duration_minutes: int | None = None
    meeting_title: str | None = None
    recurrence_expression: str | None = None
    event_id: str | None = None  # For reschedule/cancel

    # Context
    timezone: str = "UTC"
    user_id: str | None = None

    # Raw transcript for debugging
    raw_transcript: str | None = None

    def is_complete(self) -> bool:
        """Check if intent has all required information."""
        if self.intent_type == VoiceIntentType.SCHEDULE_MEETING:
            return bool(self.participants and (self.date_expression or self.time_expression))

        if self.intent_type == VoiceIntentType.CANCEL_MEETING:
            return bool(self.meeting_title or self.event_id or self.participants)

        if self.intent_type == VoiceIntentType.CHECK_AVAILABILITY:
            return bool(self.date_expression or self.time_expression)

        return True

    def get_missing_fields(self) -> list[str]:
        """Get list of missing required fields."""
        missing = []

        if self.intent_type == VoiceIntentType.SCHEDULE_MEETING:
            if not self.participants:
                missing.append("participants")
            if not self.date_expression and not self.time_expression:
                missing.append("date or time")
            if not self.duration_minutes:
                missing.append("duration")

        elif self.intent_type == VoiceIntentType.CANCEL_MEETING:
            if not self.meeting_title and not self.event_id and not self.participants:
                missing.append("meeting identifier (title, event ID, or participants)")

        return missing


@dataclass
class VoiceContext:
    """Context for voice interaction."""

    user_id: str
    tenant_id: int
    timezone: str = "UTC"
    conversation_history: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type

    # Last intent (for multi-turn conversations)
    last_intent: VoiceIntent | None = None
    pending_intent: VoiceIntent | None = None

    def add_to_history(self, role: str, content: str) -> None:
        """Add message to conversation history."""
        self.conversation_history.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Keep only last 10 messages
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
