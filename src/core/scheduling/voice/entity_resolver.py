"""
Entity Resolution for Voice UI NLP.

Converts natural language expressions to structured data:
- Relative dates ("tomorrow afternoon") -> concrete datetime
- Person references ("CTO", "my manager") -> user IDs
- Meeting references ("the 1-on-1", "standup") -> event IDs
"""

import logging
import re
from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.voice.intents import VoiceContext

logger = logging.getLogger(__name__)


class DateTimeResolver:
    """Resolve relative date/time expressions to concrete datetime objects."""

    # Time of day mappings
    TIME_OF_DAY = {
        "morning": (time(8, 0), time(12, 0)),
        "afternoon": (time(12, 0), time(17, 0)),
        "evening": (time(17, 0), time(20, 0)),
        "lunch": (time(12, 0), time(13, 0)),
        "lunchtime": (time(12, 0), time(13, 0)),
        "start of day": (time(9, 0), time(10, 0)),
        "end of day": (time(16, 0), time(17, 0)),
        "vanmiddag": (time(12, 0), time(17, 0)),  # Dutch
        "morgenochtend": (time(8, 0), time(12, 0)),  # Dutch
    }

    # Relative date patterns
    RELATIVE_DATES = {
        "today": 0,
        "tomorrow": 1,
        "morgen": 1,  # Dutch
        "day after tomorrow": 2,
        "next week": 7,
        "volgende week": 7,  # Dutch
    }

    @classmethod
    def resolve_date_expression(
        cls,
        date_expr: str,
        time_expr: str | None,
        reference_time: datetime,
        timezone: str = "UTC",
    ) -> tuple[datetime, datetime]:
        """
        Resolve date/time expression to start and end datetime.

        Args:
            date_expr: Date expression like "tomorrow", "next week"
            time_expr: Time expression like "afternoon", "2pm"
            reference_time: The current time (for relative calculations)
            timezone: User's timezone

        Returns:
            Tuple of (start_time, end_time)
        """
        date_expr = date_expr.lower().strip()

        # Calculate base date
        base_date = reference_time.date()

        # Check relative dates
        for pattern, days_offset in cls.RELATIVE_DATES.items():
            if pattern in date_expr:
                base_date = reference_time.date() + timedelta(days=days_offset)
                break

        # Check for weekday names
        weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        weekdays_nl = [
            "maandag",
            "dinsdag",
            "woensdag",
            "donderdag",
            "vrijdag",
            "zaterdag",
            "zondag",
        ]
        all_weekdays = weekdays + weekdays_nl

        for i, day in enumerate(all_weekdays):
            if day in date_expr:
                target_weekday = i % 7  # Normalize to 0-6
                current_weekday = reference_time.weekday()
                days_ahead = target_weekday - current_weekday

                # If it's already past this weekday, go to next week
                if days_ahead <= 0:
                    days_ahead += 7

                # Handle "next [weekday]"
                if "next" in date_expr or "volgende" in date_expr:
                    days_ahead += 7

                base_date = reference_time.date() + timedelta(days=days_ahead)
                break

        # Resolve time
        start_time, end_time = cls._resolve_time(time_expr, reference_time)

        # Combine date and time
        start_dt = datetime.combine(base_date, start_time)
        end_dt = datetime.combine(base_date, end_time)

        return start_dt, end_dt

    @classmethod
    def _resolve_time(cls, time_expr: str | None, reference_time: datetime) -> tuple[time, time]:
        """Resolve time expression to start and end times."""
        if not time_expr:
            # Default to next hour
            next_hour = reference_time.hour + 1
            if next_hour >= 17:  # After 5pm, default to tomorrow 9am
                return time(9, 0), time(10, 0)
            return time(next_hour, 0), time(next_hour + 1, 0)

        time_expr = time_expr.lower().strip()

        # Check time of day patterns
        for pattern, (start, end) in cls.TIME_OF_DAY.items():
            if pattern in time_expr:
                return start, end

        # Parse explicit times like "2pm", "14:00"
        # Pattern: HH:MM or H:MM with optional am/pm
        time_match = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", time_expr)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            # Handle am/pm
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            return time(hour, minute), time(hour + 1, minute)

        # Default fallback
        return time(9, 0), time(10, 0)


class PersonResolver:
    """Resolve person references to user IDs."""

    ROLE_MAPPINGS = {
        "cto": ["cto", "chief technology officer", "tech lead"],
        "ceo": ["ceo", "chief executive officer", "director"],
        "cfo": ["cfo", "chief financial officer"],
        "manager": ["manager", "team lead", "lead"],
        "my manager": ["manager"],
    }

    @classmethod
    async def resolve_person(
        cls, person_ref: str, context: VoiceContext, db_session: AsyncSession | None = None
    ) -> str | None:
        """
        Resolve person reference to user ID.

        Args:
            person_ref: Person reference like "CTO", "Alex", "my manager"
            context: Voice context with user info
            db_session: Database session for lookups (optional)

        Returns:
            User ID if found, None otherwise
        """
        person_ref = person_ref.lower().strip()

        # Check role mappings
        for role, aliases in cls.ROLE_MAPPINGS.items():
            if person_ref in aliases or any(alias in person_ref for alias in aliases):
                # TODO: Look up actual user with this role from database
                logger.info(f"Role lookup needed for: {role}")
                return None

        # Check for name patterns
        name_match = re.search(r"([a-z]+)\s*([a-z]+)?", person_ref)
        if name_match:
            first_name = name_match.group(1)
            last_name = name_match.group(2)
            # TODO: Search users by name
            logger.info(f"Name lookup needed: {first_name} {last_name or ''}")

        return None


class MeetingResolver:
    """Resolve meeting references to event IDs."""

    MEETING_TYPE_PATTERNS = {
        "1-on-1": ["1-on-1", "1 on 1", "one on one", "een-op-een"],
        "standup": ["standup", "stand-up", "daily", "dagelijkse"],
        "review": ["review", "retrospective", "retro"],
        "planning": ["planning", "sprint planning"],
    }

    @classmethod
    async def resolve_meeting(
        cls, meeting_ref: str, context: VoiceContext, db_session: AsyncSession | None = None
    ) -> str | None:
        """
        Resolve meeting reference to event ID.

        Args:
            meeting_ref: Meeting reference like "the 1-on-1", "standup"
            context: Voice context
            db_session: Database session (optional)

        Returns:
            Event ID if found, None otherwise
        """
        meeting_ref = meeting_ref.lower().strip()

        # Identify meeting type
        meeting_type = None
        for mtype, patterns in cls.MEETING_TYPE_PATTERNS.items():
            if any(pattern in meeting_ref for pattern in patterns):
                meeting_type = mtype
                break

        # Look for person reference (e.g., "1-on-1 with CTO")
        person_ref = None
        person_match = re.search(r"(?:with|met)\s+([a-z\s]+)", meeting_ref)
        if person_match:
            person_ref = person_match.group(1).strip()

        logger.info(f"Meeting lookup: type={meeting_type}, person={person_ref}")

        # TODO: Query database for matching events
        # - Search upcoming events for user
        # - Filter by meeting type and/or person
        # - Return best match

        return None

    @classmethod
    def extract_meeting_reference(cls, transcript: str) -> str | None:
        """Extract meeting reference from transcript.

        Args:
            transcript: Raw voice transcript text

        Returns:
            Meeting reference string if found, None otherwise
        """
        patterns = [
            r"(?:the\s+)?(1-on-1\s+(?:with\s+)?[a-z\s]+)",
            r"(?:the\s+)?(standup|daily)",
            r"(?:the\s+)?(sprint\s+planning)",
            r"(?:the\s+)?(review|retrospective)",
            r"(?:my\s+)?(meeting\s+(?:with\s+)?[a-z\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None
