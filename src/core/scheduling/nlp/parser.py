"""Natural Language Parser for scheduling requests.

Combines intent classification, entity extraction, and context management
to parse natural language into structured scheduling requests.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.core.scheduling.nlp.context import ContextManager, ConversationContext
from src.core.scheduling.nlp.entities import EntityExtractor, EntityType
from src.core.scheduling.nlp.intents import ClassifiedIntent, IntentClassifier, IntentType

logger = logging.getLogger(__name__)


@dataclass
class ParsedSchedulingRequest:
    """Result of parsing natural language into a scheduling request."""

    # Original input
    original_text: str

    # Classified intent
    intent: ClassifiedIntent

    # Extracted entities
    entities: dict[EntityType, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    # Parsed scheduling parameters
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration: timedelta | None = None
    participants: list[str] = field(default_factory=list)
    location: str | None = None
    description: str | None = None
    priority: int = 3  # Default medium priority
    recurrence: str | None = None

    # Status
    is_complete: bool = False
    missing_info: list[str] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=list)

    # Context reference
    session_id: str | None = None

    def to_scheduling_request(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to API scheduling request format."""
        return {
            "title": self.title or "Meeting",
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "participants": self.participants,
            "location": self.location,
            "description": self.description or self.original_text,
            "priority": self.priority,
            "recurrence": self.recurrence,
        }


@dataclass
class ParseResult:
    """Result of natural language parsing with conversation handling."""

    # The parsed request
    request: ParsedSchedulingRequest

    # Conversation handling
    requires_clarification: bool = False
    clarification_question: str | None = None

    # Follow-up information
    follow_up_suggestions: list[str] = field(default_factory=list)

    # Success status
    success: bool = True
    error_message: str | None = None


class NaturalLanguageParser:
    """Main parser for natural language scheduling requests.

    Coordinates intent classification, entity extraction, and context
    management to provide a complete parsing solution.
    """

    # Default durations by meeting type
    DEFAULT_DURATIONS = {
        "standup": timedelta(minutes=15),
        "1on1": timedelta(minutes=30),
        "planning": timedelta(minutes=60),
        "retrospective": timedelta(minutes=60),
        "review": timedelta(minutes=30),
        "interview": timedelta(minutes=45),
        "demo": timedelta(minutes=30),
        "default": timedelta(minutes=30),
    }

    # Required entities by intent
    REQUIRED_ENTITIES = {
        IntentType.SCHEDULE: [EntityType.DATE, EntityType.TIME],
        IntentType.RESCHEDULE: [EntityType.DATE, EntityType.TIME],
        IntentType.CANCEL: [EntityType.DATE],
        IntentType.QUERY_AVAILABILITY: [EntityType.PARTICIPANT],
        IntentType.QUERY_CONFLICTS: [EntityType.DATE, EntityType.TIME],
        IntentType.LIST_EVENTS: [],
        IntentType.UPDATE: [EntityType.DATE],
    }

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        """Initialize the parser.

        Args:
            context_manager: Optional context manager for conversation state
            reference_time: Reference time for relative date parsing
        """
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor(reference_time=reference_time)
        self.context_manager = context_manager or ContextManager()
        self.reference_time = reference_time or datetime.now(timezone.utc)

    async def parse(
        self,
        text: str,
        session_id: str,
        user_id: str,
        tenant_id: int,
    ) -> ParseResult:
        """Parse natural language text into a scheduling request.

        Args:
            text: Natural language input
            session_id: Conversation session ID
            user_id: User identifier
            tenant_id: Tenant identifier

        Returns:
            ParseResult with parsed request and conversation state
        """
        try:
            # Get or create conversation context
            context = await self.context_manager.get_or_create(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )

            # Add user message to context
            context.add_message("user", text)

            # Check if this is a response to a clarification question
            if context.pending_questions:
                return await self._handle_clarification(context, text)

            # Classify intent
            intent = self.intent_classifier.classify(text)
            context.current_intent = intent.intent_type.name

            # Extract entities
            entities = self.entity_extractor.extract_all(text)
            for entity in entities:
                context.add_entity(entity.entity_type, entity.value)

            # Build parsed request
            request = self._build_request(text, intent, entities, context)

            # Check for missing required information
            missing = self._check_missing_entities(intent.intent_type, context)
            if missing:
                request.missing_info = [e.name for e in missing]
                request.is_complete = False

                # Generate clarification questions
                questions = self._generate_clarification_questions(missing, context)
                request.suggested_questions = questions

                # Store pending questions
                for q in questions:
                    context.add_pending_question(q)

                # Check if we can ask clarification
                if context.can_ask_clarification():
                    context.increment_clarification_attempt()
                    await self.context_manager.save(context)

                    return ParseResult(
                        request=request,
                        requires_clarification=True,
                        clarification_question=questions[0],
                        follow_up_suggestions=questions[1:],
                    )
                else:
                    # Max clarification attempts reached
                    request.is_complete = True

            else:
                request.is_complete = True

            # Reset clarification counter on success
            context.clarification_attempts = 0
            context.reset_draft()
            context.add_message(
                "assistant",
                f"Parsed as {intent.intent_type.name}",
                {"parsed_request": request.to_scheduling_request()},
            )
            await self.context_manager.save(context)

            return ParseResult(
                request=request,
                requires_clarification=False,
            )

        except Exception as e:
            logger.exception(f"Error parsing text: {text}")
            return ParseResult(
                request=ParsedSchedulingRequest(
                    original_text=text,
                    intent=ClassifiedIntent(
                        intent_type=IntentType.UNKNOWN,
                        confidence=0.0,
                        matched_keywords=[],
                        original_text=text,
                    ),
                ),
                success=False,
                error_message=f"Failed to parse request: {str(e)}",
            )

    async def _handle_clarification(self, context: ConversationContext, text: str) -> ParseResult:
        """Handle user response to clarification question.

        Args:
            context: Current conversation context
            text: User's response

        Returns:
            ParseResult with updated request
        """
        # Extract entities from clarification response
        new_entities = self.entity_extractor.extract_all(text)
        for entity in new_entities:
            context.add_entity(entity.entity_type, entity.value)

        # Resolve the answered question
        context.resolve_question()

        # Rebuild request with new information
        intent = ClassifiedIntent(
            intent_type=IntentType[context.current_intent or "UNKNOWN"],
            confidence=1.0,
            matched_keywords=[],
            original_text=text,
        )

        # Get all entities from context
        all_entities = []
        for entity_type, value in context.extracted_entities.items():
            all_entities.append(
                type(
                    "Entity",
                    (),
                    {
                        "entity_type": entity_type,
                        "value": value,
                        "raw_text": "",
                        "start_pos": 0,
                        "end_pos": 0,
                    },
                )()
            )

        request = self._build_request(text, intent, all_entities, context)

        # Check if we still have missing info
        missing = self._check_missing_entities(intent.intent_type, context)
        if missing:
            request.missing_info = [e.name for e in missing]
            request.is_complete = False

            questions = self._generate_clarification_questions(missing, context)
            request.suggested_questions = questions

            if context.can_ask_clarification():
                context.increment_clarification_attempt()
                await self.context_manager.save(context)

                return ParseResult(
                    request=request,
                    requires_clarification=True,
                    clarification_question=questions[0],
                    follow_up_suggestions=questions[1:],
                )

        # All required info gathered
        request.is_complete = True
        context.reset_draft()
        await self.context_manager.save(context)

        return ParseResult(
            request=request,
            requires_clarification=False,
        )

    def _build_request(
        self,
        text: str,
        intent: ClassifiedIntent,
        entities: list[Any],  # TODO(TYPE): replace Any with concrete type
        context: ConversationContext,
    ) -> ParsedSchedulingRequest:
        """Build a parsed request from extracted information."""
        request = ParsedSchedulingRequest(
            original_text=text,
            intent=intent,
            session_id=context.session_id,
        )

        # Build entities dictionary
        entity_dict: dict[EntityType, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for entity in entities:
            entity_dict[entity.entity_type] = entity.value
        request.entities = entity_dict

        # Extract date/time
        if EntityType.DATETIME in entity_dict:
            request.start_time = entity_dict[EntityType.DATETIME]
        elif EntityType.DATE in entity_dict:
            date_val = entity_dict[EntityType.DATE]
            if isinstance(date_val, datetime):
                request.start_time = date_val

        # Extract duration
        if EntityType.DURATION in entity_dict:
            request.duration = entity_dict[EntityType.DURATION]

        # Extract participants
        if EntityType.PARTICIPANT in entity_dict:
            participants = entity_dict[EntityType.PARTICIPANT]
            if isinstance(participants, list):
                request.participants = participants
            else:
                request.participants = [participants]

        # Extract location
        if EntityType.LOCATION in entity_dict:
            request.location = entity_dict[EntityType.LOCATION]

        # Extract meeting type and set default title/duration
        meeting_type = entity_dict.get(EntityType.MEETING_TYPE, "default")
        if meeting_type:
            request.title = self._generate_title(meeting_type, request.participants)
            if not request.duration:
                request.duration = self.DEFAULT_DURATIONS.get(
                    meeting_type, self.DEFAULT_DURATIONS["default"]
                )

        # Extract priority
        if EntityType.PRIORITY in entity_dict:
            priority = entity_dict[EntityType.PRIORITY]
            if priority == "high":
                request.priority = 1
            elif priority == "low":
                request.priority = 5

        # Extract recurrence
        if EntityType.RECURRENCE in entity_dict:
            request.recurrence = entity_dict[EntityType.RECURRENCE]

        # Calculate end time
        if request.start_time and request.duration:
            request.end_time = request.start_time + request.duration

        # Generate description
        request.description = self._generate_description(request)

        return request

    def _check_missing_entities(
        self, intent_type: IntentType, context: ConversationContext
    ) -> list[EntityType]:
        """Check which required entities are missing."""
        required = self.REQUIRED_ENTITIES.get(intent_type, [])
        missing = []

        for entity_type in required:
            if not context.has_entity(entity_type):
                missing.append(entity_type)

        return missing

    def _generate_clarification_questions(
        self, missing_entities: list[EntityType], context: ConversationContext
    ) -> list[str]:
        """Generate questions to ask for missing information."""
        questions = []

        entity_questions = {
            EntityType.DATE: [
                "What date would you like to schedule this for?",
                "When would you like to meet?",
                "Which day works for you?",
            ],
            EntityType.TIME: [
                "What time works best?",
                "At what time should I schedule this?",
                "What time would you prefer?",
            ],
            EntityType.DURATION: [
                "How long should this meeting be?",
                "What's the expected duration?",
            ],
            EntityType.PARTICIPANT: [
                "Who should be invited to this meeting?",
                "Who else needs to attend?",
                "Who should I include?",
            ],
            EntityType.LOCATION: [
                "Where should this meeting take place?",
                "What location works best?",
            ],
        }

        for entity_type in missing_entities:
            if entity_type in entity_questions:
                # Get first available question
                questions.append(entity_questions[entity_type][0])

        return questions

    def _generate_title(self, meeting_type: str, participants: list[str]) -> str:
        """Generate a default meeting title."""
        type_titles = {
            "standup": "Daily Standup",
            "1on1": "1:1 Meeting",
            "planning": "Sprint Planning",
            "retrospective": "Sprint Retrospective",
            "review": "Code Review",
            "interview": "Interview",
            "demo": "Demo",
        }

        base_title = type_titles.get(meeting_type, "Meeting")

        if participants:
            names = ", ".join(participants[:2])
            if len(participants) > 2:
                names += f" +{len(participants) - 2}"
            return f"{base_title} with {names}"

        return base_title

    def _generate_description(self, request: ParsedSchedulingRequest) -> str:
        """Generate a description from the parsed request."""
        parts = []

        if request.intent.intent_type == IntentType.SCHEDULE:
            parts.append("Meeting scheduled via natural language processing.")
        elif request.intent.intent_type == IntentType.RESCHEDULE:
            parts.append("Meeting rescheduled.")
        elif request.intent.intent_type == IntentType.CANCEL:
            parts.append("Meeting cancelled.")

        if request.participants:
            parts.append(f"Participants: {', '.join(request.participants)}")

        if request.original_text:
            parts.append(f"Original request: {request.original_text}")

        return "\n".join(parts)

    async def get_context(self, session_id: str) -> ConversationContext | None:
        """Get the conversation context for a session.

        Args:
            session_id: Session identifier

        Returns:
            ConversationContext if found, None otherwise
        """
        return await self.context_manager.get(session_id)

    async def reset_context(self, session_id: str) -> bool:
        """Reset the conversation context for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if context was reset, False if not found
        """
        return await self.context_manager.delete(session_id)
