"""Entity extraction for scheduling natural language.

Extracts dates, times, participants, locations, and durations from text.
Uses regex patterns and dateutil for parsing.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Optional

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Types of entities that can be extracted."""

    DATE = auto()
    TIME = auto()
    DATETIME = auto()
    DURATION = auto()
    PARTICIPANT = auto()
    LOCATION = auto()
    MEETING_TYPE = auto()
    RECURRENCE = auto()
    PRIORITY = auto()
    UNKNOWN = auto()


@dataclass
class ExtractedEntity:
    """An entity extracted from natural language."""

    entity_type: EntityType
    value: str | datetime | timedelta | list[str]
    raw_text: str
    start_pos: int
    end_pos: int
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class EntityExtractor:
    """Extracts scheduling-related entities from text.

    Combines regex patterns with date parsing for comprehensive extraction.
    """

    # Duration patterns (e.g., "30 minutes", "1 hour", "2h")
    DURATION_PATTERNS = [
        (
            re.compile(r"\b(\d+)\s*(min|minute|minutes|m)\b", re.IGNORECASE),
            "minutes",
        ),
        (
            re.compile(r"\b(\d+)\s*(hr|hour|hours|h)\b", re.IGNORECASE),
            "hours",
        ),
        (
            re.compile(r"\b(half\s+an?\s+hour|30\s*min)\b", re.IGNORECASE),
            "30min",
        ),
        (
            re.compile(r"\b(an?\s+hour|1\s*h)\b", re.IGNORECASE),
            "1hour",
        ),
        (
            re.compile(r"\b(quarter\s+hour|15\s*min)\b", re.IGNORECASE),
            "15min",
        ),
    ]

    # Participant patterns - expanded for more coverage
    PARTICIPANT_PATTERNS = [
        # "with John and Jane"
        re.compile(
            r"\bwith\s+((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s+|\s+and\s+|\s*&\s*|\s+)?)+)",
            re.IGNORECASE,
        ),
        # "invite John, Jane"
        re.compile(
            r"\binvite\s+((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s+|\s+and\s+|\s*&\s*|\s+)?)+)",
            re.IGNORECASE,
        ),
        # "add John to the meeting"
        re.compile(
            r"\badd\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+to\b",
            re.IGNORECASE,
        ),
        # Email patterns
        re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"),
        # "include John and Jane"
        re.compile(
            r"\binclude\s+((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s+|\s+and\s+|\s*&\s*|\s+)?)+)",
            re.IGNORECASE,
        ),
        # "cc John" or "copy Jane"
        re.compile(
            r"\b(cc|copy)\s+((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s+|\s+and\s+|\s*&\s*|\s+)?)+)",
            re.IGNORECASE,
        ),
        # "bring John" or "have Jane join"
        re.compile(
            r"\b(bring|have)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:join|attend|come)",
            re.IGNORECASE,
        ),
        # "get John" (e.g., "get John to join")
        re.compile(
            r"\bget\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+to\s+(?:join|attend)",
            re.IGNORECASE,
        ),
        # "ask John" (e.g., "ask John to come")
        re.compile(
            r"\bask\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+to\s+(?:join|attend|come)",
            re.IGNORECASE,
        ),
    ]

    # Location patterns
    LOCATION_PATTERNS = [
        # "in Conference Room A"
        re.compile(
            r"\bin\s+(?:the\s+)?((?:Conference Room|Meeting Room|Room|Office)\s+[A-Z0-9]+)\b",
            re.IGNORECASE,
        ),
        # "at location X"
        re.compile(
            r"\bat\s+((?:Zoom|Teams|Google Meet|Skype|the\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            re.IGNORECASE,
        ),
        # "in Building X"
        re.compile(
            r"\bin\s+(?:the\s+)?([A-Z][a-z]+\s+(?:Building|Tower|Floor|Suite))\b",
            re.IGNORECASE,
        ),
    ]

    # Meeting type patterns
    MEETING_TYPE_PATTERNS = [
        (re.compile(r"\b(standup|stand-up|daily)\b", re.IGNORECASE), "standup"),
        (re.compile(r"\b(1:1|one-on-one|1-on-1)\b", re.IGNORECASE), "1on1"),
        (
            re.compile(r"\b(sprint planning|planning)\b", re.IGNORECASE),
            "planning",
        ),
        (
            re.compile(r"\b(retro|retrospective)\b", re.IGNORECASE),
            "retrospective",
        ),
        (re.compile(r"\b(review|code review)\b", re.IGNORECASE), "review"),
        (re.compile(r"\b(interview|screening)\b", re.IGNORECASE), "interview"),
        (re.compile(r"\b(demo|presentation)\b", re.IGNORECASE), "demo"),
    ]

    # Recurrence patterns
    RECURRENCE_PATTERNS = [
        (re.compile(r"\b(every day|daily)\b", re.IGNORECASE), "DAILY"),
        (re.compile(r"\b(every week|weekly)\b", re.IGNORECASE), "WEEKLY"),
        (re.compile(r"\b(every month|monthly)\b", re.IGNORECASE), "MONTHLY"),
        (
            re.compile(
                r"\b(every (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
                re.IGNORECASE,
            ),
            "WEEKLY",
        ),
        (
            re.compile(r"\b(Mon|Tu|Wed|Thu|Fri)s?\b", re.IGNORECASE),
            "WEEKLY",
        ),
    ]

    # Priority patterns
    PRIORITY_PATTERNS = [
        (
            re.compile(r"\b(high priority|urgent|asap|important)\b", re.IGNORECASE),
            "high",
        ),
        (re.compile(r"\b(low priority|low-priority)\b", re.IGNORECASE), "low"),
    ]

    # Relative date patterns
    RELATIVE_DATES = {
        "today": timedelta(days=0),
        "tomorrow": timedelta(days=1),
        "day after tomorrow": timedelta(days=2),
        "next week": timedelta(weeks=1),
        "in a week": timedelta(weeks=1),
        "next month": relativedelta(months=1),
    }

    def __init__(self, reference_time: datetime | None = None) -> None:
        """Initialize the entity extractor.

        Args:
            reference_time: Base time for relative date parsing (default: now)
        """
        self.reference_time = reference_time or datetime.now(tz=timezone.utc)

    def extract_all(self, text: str) -> list[ExtractedEntity]:
        """Extract all entities from text.

        Args:
            text: Natural language input

        Returns:
            List of extracted entities
        """
        entities: list[ExtractedEntity] = []

        # Extract each entity type
        entities.extend(self.extract_datetime(text))
        entities.extend(self.extract_duration(text))
        entities.extend(self.extract_participants(text))
        entities.extend(self.extract_location(text))
        entities.extend(self.extract_meeting_type(text))
        entities.extend(self.extract_recurrence(text))
        entities.extend(self.extract_priority(text))

        # Sort by position in text
        entities.sort(key=lambda e: e.start_pos)

        return entities

    def extract_datetime(self, text: str) -> list[ExtractedEntity]:
        """Extract date and time entities from text.

        Uses dateutil parser with relative date handling.
        """
        entities: list[ExtractedEntity] = []

        # First check for relative dates
        for phrase, delta in self.RELATIVE_DATES.items():
            pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
            for match in pattern.finditer(text):
                if isinstance(delta, timedelta):
                    date_value = self.reference_time + delta
                elif isinstance(delta, relativedelta):
                    date_value = self.reference_time + delta
                else:
                    continue

                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.DATE,
                        value=date_value.replace(hour=0, minute=0, second=0, microsecond=0),
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.95,
                    )
                )

        # Use dateutil parser for other date/time patterns
        # Common patterns to try
        date_patterns = [
            # "March 15 at 3pm"
            r"\b([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?(?:,? \d{4})?\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
            # "next Monday at 2pm"
            r"\b(next\s+[A-Za-z]+(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)\b",
            # "at 3pm"
            r"\b(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
            # ISO date patterns
            r"\b(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?)\b",
        ]

        for pattern_str in date_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            for match in pattern.finditer(text):
                try:
                    parsed = date_parser.parse(
                        match.group(1),
                        default=self.reference_time,
                        fuzzy=True,
                    )
                    # Ensure timezone aware
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)

                    entity_type = (
                        EntityType.DATETIME
                        if parsed.hour != 0 or parsed.minute != 0
                        else EntityType.DATE
                    )

                    entities.append(
                        ExtractedEntity(
                            entity_type=entity_type,
                            value=parsed,
                            raw_text=match.group(0),
                            start_pos=match.start(),
                            end_pos=match.end(),
                            confidence=0.85,
                        )
                    )
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse date '{match.group(1)}': {e}")

        return entities

    def extract_duration(self, text: str) -> list[ExtractedEntity]:
        """Extract duration entities from text."""
        entities: list[ExtractedEntity] = []

        for pattern, unit in self.DURATION_PATTERNS:
            for match in pattern.finditer(text):
                raw_text = match.group(0)

                if unit == "30min":
                    duration = timedelta(minutes=30)
                elif unit == "1hour":
                    duration = timedelta(hours=1)
                elif unit == "15min":
                    duration = timedelta(minutes=15)
                elif unit == "minutes":
                    minutes = int(match.group(1))
                    duration = timedelta(minutes=minutes)
                elif unit == "hours":
                    hours = int(match.group(1))
                    duration = timedelta(hours=hours)
                else:
                    continue

                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.DURATION,
                        value=duration,
                        raw_text=raw_text,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.9,
                        metadata={"unit": unit},
                    )
                )

        return entities

    def extract_participants(self, text: str) -> list[ExtractedEntity]:
        """Extract participant names and emails from text."""
        entities: list[ExtractedEntity] = []
        found_names: set[str] = set()

        for pattern in self.PARTICIPANT_PATTERNS:
            for match in pattern.finditer(text):
                raw_text = match.group(0)

                # Check if it's an email
                if "@" in raw_text:
                    entities.append(
                        ExtractedEntity(
                            entity_type=EntityType.PARTICIPANT,
                            value=[raw_text],
                            raw_text=raw_text,
                            start_pos=match.start(),
                            end_pos=match.end(),
                            confidence=1.0,
                            metadata={"type": "email"},
                        )
                    )
                else:
                    # Parse names (handle "John, Jane and Jim" or "John & Jane")
                    # For patterns with multiple groups, use the last non-empty group
                    if len(match.groups()) > 1:
                        # Find the first non-empty group
                        names_text = next((g for g in match.groups() if g), raw_text)
                    else:
                        names_text = match.group(1) if match.groups() else raw_text

                    names = re.split(r",\s+|\s+and\s+|\s*&\s+|\s+", names_text)
                    names = [n.strip() for n in names if n.strip() and len(n.strip()) > 1]

                    # Filter out common words that are not names
                    exclude_words = {
                        "with",
                        "invite",
                        "add",
                        "to",
                        "include",
                        "cc",
                        "copy",
                        "bring",
                        "have",
                        "get",
                        "ask",
                        "join",
                        "attend",
                        "come",
                        "the",
                        "meeting",
                        "a",
                        "an",
                    }
                    names = [n for n in names if n.lower() not in exclude_words]

                    # Filter out duplicates
                    names = [n for n in names if n.lower() not in found_names]
                    found_names.update(n.lower() for n in names)

                    if names:
                        entities.append(
                            ExtractedEntity(
                                entity_type=EntityType.PARTICIPANT,
                                value=names,
                                raw_text=raw_text,
                                start_pos=match.start(),
                                end_pos=match.end(),
                                confidence=0.8,
                                metadata={"type": "name"},
                            )
                        )

        return entities

    def extract_location(self, text: str) -> list[ExtractedEntity]:
        """Extract location from text."""
        entities: list[ExtractedEntity] = []

        for pattern in self.LOCATION_PATTERNS:
            for match in pattern.finditer(text):
                location = match.group(1).strip()
                # Clean up "the" prefix
                location = re.sub(r"^the\s+", "", location, flags=re.IGNORECASE)

                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.LOCATION,
                        value=location,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.75,
                    )
                )

        return entities

    def extract_meeting_type(self, text: str) -> list[ExtractedEntity]:
        """Extract meeting type from text."""
        entities: list[ExtractedEntity] = []

        for pattern, meeting_type in self.MEETING_TYPE_PATTERNS:
            for match in pattern.finditer(text):
                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.MEETING_TYPE,
                        value=meeting_type,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.9,
                    )
                )

        return entities

    def extract_recurrence(self, text: str) -> list[ExtractedEntity]:
        """Extract recurrence patterns from text."""
        entities: list[ExtractedEntity] = []

        for pattern, recurrence_type in self.RECURRENCE_PATTERNS:
            for match in pattern.finditer(text):
                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.RECURRENCE,
                        value=recurrence_type,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.85,
                    )
                )

        return entities

    def extract_priority(self, text: str) -> list[ExtractedEntity]:
        """Extract priority from text."""
        entities: list[ExtractedEntity] = []

        for pattern, priority in self.PRIORITY_PATTERNS:
            for match in pattern.finditer(text):
                entities.append(
                    ExtractedEntity(
                        entity_type=EntityType.PRIORITY,
                        value=priority,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.8,
                    )
                )

        return entities

    def get_missing_entities(self, text: str, required: list[EntityType]) -> list[EntityType]:
        """Determine which required entities are missing.

        Args:
            text: Natural language input
            required: List of required entity types

        Returns:
            List of missing entity types
        """
        extracted = self.extract_all(text)
        found_types = {e.entity_type for e in extracted}
        return [r for r in required if r not in found_types]
