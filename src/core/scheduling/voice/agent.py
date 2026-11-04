"""
Voice agent for hands-free scheduling using OODA loop.

Observe-Orient-Decide-Act pattern for voice interaction.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.smart.service import SmartSchedulingService
from src.core.scheduling.voice.intents import VoiceContext, VoiceIntent, VoiceIntentType
from src.core.scheduling.voice.nlu import VoiceIntentParser
from src.core.types import AgentType

logger = logging.getLogger(__name__)


@dataclass
class VoiceActionResult:
    """Result of a voice action."""

    success: bool
    response_text: str
    action_type: str
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    requires_follow_up: bool = False
    suggested_responses: list[str] | None = None
    error_message: str | None = None


class SchedulingVoiceAgent(EnhancedBaseAgent):
    """
    Agentic voice interface for scheduling operations.

    Uses OODA loop pattern internally:
    - Observe: Parse voice input, extract entities
    - Orient: Determine intent, validate constraints
    - Decide: Choose scheduling strategy
    - Act: Execute scheduling operation, generate response
    """

    provider = "native"
    model = "scheduling-voice-v1"

    def __init__(self, tenant_id: int, db: AsyncSession, **kwargs: Any) -> None:
        super().__init__(
            agent_id="scheduling_voice_agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id,
            **kwargs,
        )
        self.db = db
        self.intent_parser = VoiceIntentParser(db)
        self.smart_service = SmartSchedulingService(db)

    # ========================================================================
    # OODA Loop Implementation
    # ========================================================================

    async def process_voice_input(
        self,
        transcript: str,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """
        Process voice input through OODA loop.

        This is the main entry point for voice interactions.
        """
        # O - Observe: Parse the input
        intent = await self._observe(transcript, context)
        logger.info(
            f"Voice intent detected: {intent.intent_type.value} (confidence: {intent.confidence:.2f})"
        )

        # O - Orient: Validate and determine approach
        orientation = self._orient(intent, context)
        if orientation["action"] == "clarify":
            return await self._handle_clarification(intent, orientation)

        # D - Decide: Choose execution strategy
        decision = self._decide(intent, orientation)

        # A - Act: Execute and generate response
        return await self._act(decision, intent, context)

    async def _observe(self, transcript: str, context: VoiceContext) -> VoiceIntent:
        """
        Observe phase: Parse voice input and extract entities.
        """
        # Check if this is a follow-up to a pending intent
        if context.pending_intent:
            # Merge new information with pending intent
            return await self._merge_with_pending(transcript, context)

        # Parse fresh intent
        return await self.intent_parser.parse(transcript, context)

    def _orient(self, intent: VoiceIntent, context: VoiceContext) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Orient phase: Validate constraints and determine approach.
        """
        # Check if we have enough information
        missing = intent.get_missing_fields()

        if missing:
            return {
                "action": "clarify",
                "missing_fields": missing,
                "confidence": intent.confidence,
            }

        # Check confidence threshold
        if intent.confidence < 0.5:
            return {
                "action": "clarify",
                "reason": "low_confidence",
                "confidence": intent.confidence,
            }

        # Determine if we can auto-execute
        auto_execute = intent.confidence > 0.8 and intent.intent_type in (
            VoiceIntentType.SCHEDULE_MEETING,
            VoiceIntentType.CANCEL_MEETING,
            VoiceIntentType.CHECK_AVAILABILITY,
        )

        return {
            "action": "execute" if auto_execute else "confirm",
            "intent_type": intent.intent_type,
            "confidence": intent.confidence,
        }

    def _decide(self, intent: VoiceIntent, orientation: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Decide phase: Choose execution strategy.
        """
        action = orientation["action"]

        if action == "clarify":
            return {"action": "ask_clarification"}

        if action == "confirm":
            return {"action": "ask_confirmation"}

        # Map intent to action
        intent_actions = {
            VoiceIntentType.SCHEDULE_MEETING: "create_meeting",
            VoiceIntentType.RESCHEDULE_MEETING: "reschedule_meeting",
            VoiceIntentType.CANCEL_MEETING: "cancel_meeting",
            VoiceIntentType.CHECK_AVAILABILITY: "check_availability",
            VoiceIntentType.LIST_MEETINGS: "list_meetings",
            VoiceIntentType.SUGGEST_TIMES: "suggest_times",
            VoiceIntentType.BLOCK_FOCUS_TIME: "block_focus_time",
        }

        return {
            "action": intent_actions.get(intent.intent_type, "unknown"),
            "intent": intent,
        }

    async def _act(
        self,
        decision: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """
        Act phase: Execute decision and generate response.
        """
        action = decision["action"]

        if action == "ask_clarification":
            return await self._handle_clarification(intent, decision)

        if action == "ask_confirmation":
            return self._generate_confirmation_request(intent)

        # Execute scheduling action
        if action == "create_meeting":
            return await self._create_meeting(intent, context)

        if action == "reschedule_meeting":
            return await self._reschedule_meeting(intent, context)

        if action == "cancel_meeting":
            return await self._cancel_meeting(intent, context)

        if action == "check_availability":
            return await self._check_availability(intent, context)

        if action == "suggest_times":
            return await self._suggest_times(intent, context)

        if action == "list_meetings":
            return await self._list_meetings(intent, context)

        # Handle unknown intent
        return VoiceActionResult(
            success=True,  # Changed to True - we successfully understood it's unknown
            response_text="I'm not sure what you'd like me to do. Could you rephrase that?",
            action_type="unknown",
            data={
                "intent": "unknown",
                "entities": {},
            },
            requires_follow_up=True,
        )

    # ========================================================================
    # Action Implementations
    # ========================================================================

    async def _create_meeting(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """Create a meeting based on voice intent."""
        try:
            # Parse date/time using enhanced resolver (supports Dutch)
            start_time = self.intent_parser.resolve_relative_date(
                intent.date_expression or "tomorrow",
                intent.time_expression or "",
                context.timezone,
            )

            if not start_time:
                # Fallback to simple parsing
                if intent.date_expression:
                    parsed_date = self.intent_parser.parse_date_expression(
                        intent.date_expression, context.timezone
                    )
                    date = (
                        parsed_date
                        if parsed_date is not None
                        else datetime.now(timezone.utc) + timedelta(days=1)
                    )
                else:
                    date = datetime.now(timezone.utc) + timedelta(days=1)

                if intent.time_expression:
                    time_obj = self.intent_parser.parse_time_expression(intent.time_expression)
                    if time_obj is not None:
                        start_time = datetime.combine(date.date(), time_obj)
                    else:
                        start_time = datetime.combine(
                            date.date(), datetime.min.time().replace(hour=9)
                        )
                else:
                    # Default to 9 AM
                    start_time = datetime.combine(date.date(), datetime.min.time().replace(hour=9))

            # Duration
            duration = intent.duration_minutes or 30
            end_time = start_time + timedelta(minutes=duration)

            # Title
            title = intent.meeting_title or self._generate_title(intent.participants)

            # Create event directly using the model
            event = CalendarEvent(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                organizer_id=context.user_id,
                title=title,
                description="Voice-scheduled meeting",
                start_time=start_time,
                end_time=end_time,
                event_type="meeting",
                status="scheduled",
                priority=3,
            )

            # Save to database
            self.db.add(event)
            await self.db.flush()
            await self.db.commit()

            # Generate response
            participants_str = ""
            if intent.participants:
                participants_str = f" with {', '.join(intent.participants)}"

            response = (
                f"I've scheduled '{title}'{participants_str} for "
                f"{start_time.strftime('%A, %B %d at %I:%M %p')}. "
                f"It will last {duration} minutes."
            )

            return VoiceActionResult(
                success=True,
                response_text=response,
                action_type="create_meeting",
                data={
                    "event_id": event.id,
                    "title": event.title,
                    "start_time": event.start_time.isoformat(),
                    "end_time": event.end_time.isoformat(),
                    "intent": "schedule_meeting",
                    "entities": {
                        "participants": intent.participants,
                        "date_expression": intent.date_expression,
                        "time_expression": intent.time_expression,
                        "duration_minutes": intent.duration_minutes,
                        "meeting_title": intent.meeting_title,
                    },
                },
                requires_follow_up=False,
            )

        except Exception as exc:
            logger.exception("Error creating meeting")
            return VoiceActionResult(
                success=False,
                response_text="I had trouble creating that meeting. Could you try again?",
                action_type="create_meeting",
                error_message=str(exc),
                requires_follow_up=True,
            )

    async def _cancel_meeting(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """Cancel a meeting based on voice intent."""
        from src.core.scheduling.repository import CalendarEventRepository

        repo = CalendarEventRepository(self.db)

        # Find the meeting
        if intent.event_id:
            event = await repo.get_by_id(intent.event_id, context.tenant_id)
        else:
            # Get upcoming meetings from the user
            now = datetime.now(timezone.utc)
            end_search = now + timedelta(days=30)  # Search next 30 days

            events = await repo.list_by_user_in_range(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                start=now,
                end=end_search,
            )

            if intent.meeting_title:
                # Filter by title (case-insensitive partial match)
                title_lower = intent.meeting_title.lower()
                events = [e for e in events if title_lower in e.title.lower()]

            event = events[0] if events else None

        if not event:
            return VoiceActionResult(
                success=False,
                response_text="I couldn't find that meeting. Could you be more specific?",
                action_type="cancel_meeting",
                requires_follow_up=True,
            )

        # Cancel the event
        event.status = "cancelled"
        await self.db.commit()

        return VoiceActionResult(
            success=True,
            response_text=f"I've cancelled '{event.title}' scheduled for {event.start_time.strftime('%A at %I:%M %p')}.",
            action_type="cancel_meeting",
            data={
                "event_id": event.id,
                "title": event.title,
                "intent": "cancel_event",
                "entities": {
                    "meeting_title": event.title,
                    "event_id": event.id,
                },
            },
        )

    async def _reschedule_meeting(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """Reschedule a meeting based on voice intent."""
        from src.core.scheduling.repository import CalendarEventRepository

        repo = CalendarEventRepository(self.db)

        # Find the meeting to reschedule
        event = None
        if intent.event_id:
            event = await repo.get_by_id(intent.event_id, context.tenant_id)
        else:
            # Search for matching events
            now = datetime.now(timezone.utc)
            end_search = now + timedelta(days=30)

            events = await repo.list_by_user_in_range(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                start=now,
                end=end_search,
            )

            # Filter by title if provided
            if intent.meeting_title:
                title_lower = intent.meeting_title.lower()
                events = [e for e in events if title_lower in e.title.lower()]

            # Filter by participants if provided
            if intent.participants and events:
                participant_keywords = [p.lower() for p in intent.participants]
                filtered = []
                for e in events:
                    event_text = e.title.lower()
                    if e.description:
                        event_text += " " + e.description.lower()
                    if any(pk in event_text for pk in participant_keywords):
                        filtered.append(e)
                if filtered:
                    events = filtered

            event = events[0] if events else None

        if not event:
            return VoiceActionResult(
                success=False,
                response_text="I couldn't find that meeting to reschedule. Could you be more specific?",
                action_type="reschedule_meeting",
                requires_follow_up=True,
            )

        try:
            # Parse new date/time using enhanced resolver (supports Dutch)
            new_start = self.intent_parser.resolve_relative_date(
                intent.date_expression or "tomorrow",
                intent.time_expression or "",
                context.timezone,
            )

            if not new_start:
                # Fallback to simple parsing
                if intent.date_expression:
                    parsed_date = self.intent_parser.parse_date_expression(
                        intent.date_expression, context.timezone
                    )
                    new_date = (
                        parsed_date
                        if parsed_date is not None
                        else datetime.now(timezone.utc) + timedelta(days=1)
                    )
                else:
                    new_date = datetime.now(timezone.utc) + timedelta(days=1)

                if intent.time_expression:
                    new_time = self.intent_parser.parse_time_expression(intent.time_expression)
                    if new_time is not None:
                        new_start = datetime.combine(new_date.date(), new_time)
                    else:
                        # Keep the same time
                        new_start = datetime.combine(
                            new_date.date(),
                            (
                                event.start_time.time()
                                if hasattr(event.start_time, "time")
                                else event.start_time.timetz().replace(tzinfo=None)
                            ),
                        )
                else:
                    # Keep the same time
                    new_start = datetime.combine(
                        new_date.date(),
                        (
                            event.start_time.time()
                            if hasattr(event.start_time, "time")
                            else event.start_time.timetz().replace(tzinfo=None)
                        ),
                    )

            # Calculate new end time preserving duration
            duration = (event.end_time - event.start_time).total_seconds() / 60
            new_end = new_start + timedelta(minutes=duration)

            # Update the event
            old_start = event.start_time
            event.start_time = new_start
            event.end_time = new_end
            event.updated_at = datetime.now(timezone.utc)

            await self.db.commit()

            return VoiceActionResult(
                success=True,
                response_text=(
                    f"I've rescheduled '{event.title}' from "
                    f"{old_start.strftime('%A, %B %d at %I:%M %p')} to "
                    f"{new_start.strftime('%A, %B %d at %I:%M %p')}."
                ),
                action_type="reschedule_meeting",
                data={
                    "event_id": event.id,
                    "title": event.title,
                    "old_start": old_start.isoformat(),
                    "new_start": new_start.isoformat(),
                    "new_end": new_end.isoformat(),
                    "intent": "reschedule_meeting",
                    "entities": {
                        "meeting_title": intent.meeting_title,
                        "date_expression": intent.date_expression,
                        "time_expression": intent.time_expression,
                        "participants": intent.participants,
                    },
                },
                requires_follow_up=False,
            )

        except Exception as exc:
            logger.exception("Error rescheduling meeting")
            return VoiceActionResult(
                success=False,
                response_text="I had trouble rescheduling that meeting. Could you try again?",
                action_type="reschedule_meeting",
                error_message=str(exc),
                requires_follow_up=True,
            )

    async def _check_availability(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """Check availability based on voice intent."""
        # Parse date
        if intent.date_expression:
            parsed_date = self.intent_parser.parse_date_expression(
                intent.date_expression, context.timezone
            )
            date = (
                parsed_date
                if parsed_date is not None
                else datetime.now(timezone.utc) + timedelta(days=1)
            )
        else:
            date = datetime.now(timezone.utc) + timedelta(days=1)

        # Get available slots
        slots = await self.smart_service.suggest_meeting_times(  # type: ignore[attr-defined]
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            duration_minutes=intent.duration_minutes or 30,
            preferred_date=date,
        )

        if not slots:
            return VoiceActionResult(
                success=True,
                response_text=f"You don't appear to have any availability on {date.strftime('%A')}. Would you like me to check another day?",
                action_type="check_availability",
                requires_follow_up=True,
            )

        # Format slots
        slot_times = [slot.start_time.strftime("%I:%M %p") for slot in slots[:3]]
        slots_str = ", ".join(slot_times)

        return VoiceActionResult(
            success=True,
            response_text=f"You're available at {slots_str} on {date.strftime('%A')}. Would you like me to schedule something?",
            action_type="check_availability",
            data={"available_slots": slot_times},
            requires_follow_up=True,
            suggested_responses=[
                "Yes, schedule a meeting at the first time",
                "Check another day",
                "No thanks",
            ],
        )

    async def _suggest_times(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """Suggest meeting times."""
        return await self._check_availability(intent, context)

    async def _list_meetings(
        self,
        intent: VoiceIntent,
        context: VoiceContext,
    ) -> VoiceActionResult:
        """List upcoming meetings."""
        from src.core.scheduling.repository import CalendarEventRepository

        repo = CalendarEventRepository(self.db)

        # Get upcoming meetings from the user
        now = datetime.now(timezone.utc)
        end_search = now + timedelta(days=30)  # Next 30 days

        events = await repo.list_by_user_in_range(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            start=now,
            end=end_search,
        )

        # Limit to 5 meetings
        events = events[:5]

        if not events:
            return VoiceActionResult(
                success=True,
                response_text="You don't have any upcoming meetings.",
                action_type="list_meetings",
            )

        # Format meetings
        meeting_list = []
        for event in events:
            time_str = event.start_time.strftime("%A at %I:%M %p")
            meeting_list.append(f"'{event.title}' on {time_str}")

        meetings_str = "; ".join(meeting_list)

        return VoiceActionResult(
            success=True,
            response_text=f"You have {len(events)} upcoming meetings: {meetings_str}.",
            action_type="list_meetings",
            data={"meetings": [{"id": e.id, "title": e.title} for e in events]},
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _merge_with_pending(
        self,
        transcript: str,
        context: VoiceContext,
    ) -> VoiceIntent:
        """Merge new information with pending intent."""
        # Parse new intent
        new_intent = await self.intent_parser.parse(transcript, context)

        # Merge with pending
        pending = context.pending_intent

        if not pending:
            return new_intent

        # Fill in missing fields from new intent
        if new_intent.participants:
            pending.participants = new_intent.participants
        if new_intent.date_expression:
            pending.date_expression = new_intent.date_expression
        if new_intent.time_expression:
            pending.time_expression = new_intent.time_expression
        if new_intent.duration_minutes:
            pending.duration_minutes = new_intent.duration_minutes
        if new_intent.meeting_title:
            pending.meeting_title = new_intent.meeting_title

        # Clear pending since we've merged
        context.pending_intent = None

        return pending

    async def _handle_clarification(
        self,
        intent: VoiceIntent,
        orientation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> VoiceActionResult:
        """Handle missing information by asking clarifying questions."""
        missing = orientation.get("missing_fields", [])

        if "participants" in missing:
            question = "Who would you like to meet with?"
        elif "date or time" in missing:
            question = "When would you like to schedule this?"
        elif "duration" in missing:
            question = "How long should the meeting be?"
        else:
            question = "Could you provide more details about what you'd like to schedule?"

        return VoiceActionResult(
            success=True,
            response_text=question,
            action_type="clarify",
            data={
                "intent": "clarify",
                "entities": {
                    "participants": intent.participants,
                    "date_expression": intent.date_expression,
                    "time_expression": intent.time_expression,
                    "duration_minutes": intent.duration_minutes,
                    "meeting_title": intent.meeting_title,
                },
            },
            requires_follow_up=True,
        )

    def _generate_confirmation_request(self, intent: VoiceIntent) -> VoiceActionResult:
        """Generate a confirmation request before executing."""
        participants_str = ""
        if intent.participants:
            participants_str = f" with {', '.join(intent.participants)}"

        date_str = intent.date_expression or "tomorrow"
        time_str = intent.time_expression or "9 AM"
        duration_str = f"{intent.duration_minutes or 30} minutes"

        return VoiceActionResult(
            success=True,
            response_text=f"I'll schedule a meeting{participants_str} for {date_str} at {time_str} for {duration_str}. Sound good?",
            action_type="confirm",
            data={
                "intent": "confirm",
                "entities": {
                    "participants": intent.participants,
                    "date_expression": intent.date_expression,
                    "time_expression": intent.time_expression,
                    "duration_minutes": intent.duration_minutes,
                    "meeting_title": intent.meeting_title,
                },
            },
            requires_follow_up=True,
            suggested_responses=["Yes", "No", "Change the time"],
        )

    def _generate_title(self, participants: list[str]) -> str:
        """Generate a meeting title from participants."""
        if not participants:
            return "Meeting"

        if len(participants) == 1:
            return f"Meeting with {participants[0]}"

        if len(participants) == 2:
            return f"Meeting with {participants[0]} and {participants[1]}"

        return f"Meeting with {participants[0]} and {len(participants) - 1} others"
