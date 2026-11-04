"""
Natural Language Understanding for voice scheduling.

Parses voice transcripts into structured intents with entity extraction.
Supports both English and Dutch languages.
"""

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.voice.intents import VoiceContext, VoiceIntent, VoiceIntentType

logger = logging.getLogger(__name__)


class DutchDateNormalizer:
    """
    Normalizes Dutch date/time expressions to concrete datetimes.

    Handles relative dates like "vanmiddag", "morgenochtend", "volgende week".
    """

    # Dutch time periods mapped to hours
    TIME_PERIODS = {
        "ochtend": (9, 0),  # 9:00 AM
        "morgenochtend": (9, 0),  # tomorrow morning
        "middag": (14, 0),  # 2:00 PM
        "vanmiddag": (14, 0),  # this afternoon
        "namiddag": (15, 0),  # 3:00 PM
        "avond": (18, 0),  # 6:00 PM
        "nacht": (20, 0),  # 8:00 PM
    }

    # Dutch relative dates (with offsets in days)
    RELATIVE_DATES = {
        "vandaag": 0,
        "morgen": 1,
        "overmorgen": 2,
        "gisteren": -1,
        "eergisteren": -2,
    }

    # Dutch patterns that need to be matched as whole words
    RELATIVE_DATE_PATTERNS = {
        r"\bvandaag\b": 0,
        r"\bmorgen\b": 1,
        r"\bovermorgen\b": 2,
        r"\bgisteren\b": -1,
        r"\beergisteren\b": -2,
    }

    # Dutch weekdays
    WEEKDAYS = {
        "maandag": 0,
        "dinsdag": 1,
        "woensdag": 2,
        "donderdag": 3,
        "vrijdag": 4,
        "zaterdag": 5,
        "zondag": 6,
    }

    # Dutch modifiers
    MODIFIERS = {
        "volgende": 7,  # Add a week
        "komende": 0,  # This coming
        "aankomende": 0,  # Upcoming
    }

    @classmethod
    def normalize(
        cls, text: str, base_date: datetime | None = None
    ) -> tuple[datetime | None, time | None]:
        """
        Normalize a Dutch date/time expression.

        Returns:
            Tuple of (date, time) - either may be None if not specified
        """
        if base_date is None:
            base_date = datetime.now(timezone.utc)

        text_lower = text.lower().strip()
        target_date = None
        target_time = None

        # Check for relative dates (vandaag, morgen, etc.)
        # Use regex patterns to match whole words, and check longer patterns first
        sorted_patterns = sorted(
            cls.RELATIVE_DATE_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True
        )
        for pattern, days in sorted_patterns:
            if re.search(pattern, text_lower):
                target_date = base_date + timedelta(days=days)
                break

        # Check for weekdays
        for day_name, day_num in cls.WEEKDAYS.items():
            if day_name in text_lower:
                current_day = base_date.weekday()
                days_ahead = (day_num - current_day) % 7

                # Check for modifiers like "volgende"
                if "volgende" in text_lower or "komende" in text_lower:
                    days_ahead += 7
                elif days_ahead == 0:
                    # If today, assume next week unless "vandaag" specified
                    if "vandaag" not in text_lower:
                        days_ahead = 7

                target_date = base_date + timedelta(days=days_ahead)
                break

        # Check for time periods (longer patterns first)
        sorted_periods = sorted(cls.TIME_PERIODS.items(), key=lambda x: len(x[0]), reverse=True)
        for period, (hour, minute) in sorted_periods:
            if period in text_lower:
                target_time = time(hour, minute)
                # If "morgenochtend", also set date to tomorrow
                if period == "morgenochtend":
                    target_date = base_date + timedelta(days=1)
                break

        # Check for numeric times (e.g., "2 uur", "14:00")
        time_match = re.search(r"\b(\d{1,2})\s*(?:uur|:)(\d{2})?\b", text_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            target_time = time(hour, minute)

        # Handle "volgende week" without specific day
        if "volgende week" in text_lower and target_date is None:
            target_date = base_date + timedelta(days=7)

        return target_date, target_time


class ReferenceResolver:
    """
    Resolves references like "de 1-op-1 met de CTO" to specific events.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def resolve_event_reference(
        self,
        transcript: str,
        user_id: str,
        tenant_id: int,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Resolve a reference to a specific event.

        Examples:
            - "de 1-op-1 met de CTO" -> Find 1:1 meeting with CTO
            - "mijn meeting met Alice" -> Find meeting with Alice
            - "het team overleg" -> Find team meeting
        """
        from src.core.scheduling.repository import CalendarEventRepository

        if self.db is None:
            return None

        repo = CalendarEventRepository(self.db)

        # Extract keywords from the reference
        keywords = self._extract_reference_keywords(transcript)

        if not keywords:
            return None

        # Search in upcoming events
        now = datetime.now(timezone.utc)
        end_search = now + timedelta(days=30)

        events = await repo.list_by_user_in_range(
            tenant_id=tenant_id,
            user_id=user_id,
            start=now,
            end=end_search,
        )

        # Score each event by keyword match
        scored_events = []
        for event in events:
            score = self._calculate_match_score(event, keywords)
            if score > 0:
                scored_events.append((event, score))

        # Return the best match
        if scored_events:
            scored_events.sort(key=lambda x: x[1], reverse=True)
            best_match = scored_events[0][0]
            return {
                "event_id": best_match.id,
                "title": best_match.title,
                "start_time": best_match.start_time,
                "end_time": best_match.end_time,
                "confidence": scored_events[0][1],
            }

        return None

    def _extract_reference_keywords(self, transcript: str) -> list[str]:
        """Extract searchable keywords from a reference."""
        keywords = []
        text_lower = transcript.lower()

        # Meeting type patterns
        meeting_types = [
            r"1-op-1",
            r"1:1",
            r"one on one",
            r"one-on-one",
            r"team meeting",
            r"standup",
            r"stand-up",
            r"overleg",
            r"vergadering",
        ]
        for pattern in meeting_types:
            if re.search(pattern, text_lower, re.IGNORECASE):
                keywords.append(pattern.replace(r"\-", "-"))

        # Role patterns (CTO, CEO, manager, etc.)
        role_pattern = re.compile(
            r"\b(CTO|CEO|CFO|COO|manager|director|lead|head)\b", re.IGNORECASE
        )
        for match in role_pattern.finditer(text_lower):
            keywords.append(match.group(1).lower())

        # Name patterns (capitalized words after "met" or "with")
        name_pattern = re.compile(r"(?:met|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE)
        for match in name_pattern.finditer(transcript):
            keywords.append(match.group(1).lower())

        return keywords

    def _calculate_match_score(self, event: Any, keywords: list[str]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate how well an event matches the keywords."""
        score = 0.0
        event_text = event.title.lower()
        if event.description:
            event_text += " " + event.description.lower()

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in event_text:
                # Exact match in title scores higher
                if keyword_lower in event.title.lower():
                    score += 2.0
                else:
                    score += 1.0

        # Normalize by keyword count
        if keywords:
            score = score / len(keywords)

        return min(score, 3.0)  # Cap at 3.0


class VoiceIntentParser:
    """
    Parse voice transcripts into structured intents.

    Uses pattern matching and keyword detection for intent classification
    and entity extraction. Supports English and Dutch languages.
    """

    # Intent patterns (keywords that trigger specific intents)
    INTENT_PATTERNS = {
        VoiceIntentType.SCHEDULE_MEETING: [
            # English
            r"schedule\s+(?:a\s+)?meeting",
            r"book\s+(?:a\s+)?meeting",
            r"set\s+up\s+(?:a\s+)?meeting",
            r"create\s+(?:a\s+)?meeting",
            r"plan\s+(?:a\s+)?meeting",
            r"find\s+time\s+for",
            r"arrange\s+(?:a\s+)?meeting",
            # Dutch
            r"plan\s+(?:een\s+)?(afspraak|meeting|vergadering)",
            r"maak\s+(?:een\s+)?(afspraak|meeting|vergadering)",
            r"zet\s+(?:een\s+)?(afspraak|meeting|vergadering)\s+in",
            r"plan\s+een\s+afspraak",
        ],
        VoiceIntentType.RESCHEDULE_MEETING: [
            # English
            r"reschedule\s+(?:the\s+)?meeting",
            r"move\s+(?:the\s+)?meeting",
            r"change\s+(?:the\s+)?time",
            r"postpone\s+(?:the\s+)?meeting",
            # Dutch
            r"verplaats\s+(?:de\s+)?(afspraak|meeting|vergadering)",
            r"verzet\s+(?:de\s+)?(afspraak|meeting|vergadering)",
            r"wijzig\s+(?:de\s+)?(afspraak|meeting|vergadering)",
            r"anders\s+(?:tijdstip|tijd)",
            r"verzetten\s+naar",
            r"verplaatsen\s+naar",
        ],
        VoiceIntentType.CANCEL_MEETING: [
            # English
            r"cancel\s+(?:the\s+)?meeting",
            r"delete\s+(?:the\s+)?meeting",
            r"remove\s+(?:the\s+)?meeting",
            r"call\s+off\s+(?:the\s+)?meeting",
            # Dutch
            r"annuleer\s+(?:de\s+)?(afspraak|meeting|vergadering)?",
            r"\bannuleren\b",
            r"verwijder\s+(?:de\s+)?(afspraak|meeting|vergadering)",
            r"\bafzeggen\b",
            r"\bafgelasten\b",
        ],
        VoiceIntentType.CHECK_AVAILABILITY: [
            # English
            r"when\s+(?:is|are)\s+(?:everyone\s+)?available",
            r"what\s+times?\s+(?:work|are\s+good)",
            r"check\s+availability",
            r"find\s+(?:an\s+)?available\s+(?:time|slot)",
            # Dutch
            r"wanneer\s+(?:is|ben)\s+(?:iedereen\s+)?beschikbaar",
            r"wanneer\s+heb\s+ik\s+tijd",
            r"check\s+beschikbaarheid",
            r"vrije\s+tijden",
            r"vrije\s+tijd",
        ],
        VoiceIntentType.LIST_MEETINGS: [
            # English
            r"what('s|s| are)\s+my\s+meetings",
            r"show\s+my\s+meetings",
            r"list\s+my\s+meetings",
            r"what\s+do\s+i\s+have\s+(?:today|tomorrow|this\s+week)",
            # Dutch
            r"wat\s+staat\s+er\s+op\s+mijn\s+agenda",
            r"laat\s+mijn\s+afspraken\s+zien",
            r"toon\s+mijn\s+afspraken",
            r"welke\s+afspraken\s+heb\s+ik",
        ],
        VoiceIntentType.SUGGEST_TIMES: [
            # English
            r"suggest\s+(?:some\s+)?times?",
            r"when\s+should\s+we\s+meet",
            r"what\s+time\s+works",
            # Dutch
            r"suggesteer\s+tijden",
            r"wanneer\s+kunnen\s+we\s+afspreken",
        ],
        VoiceIntentType.BLOCK_FOCUS_TIME: [
            # English
            r"block\s+(?:some\s+)?focus\s+time",
            r"schedule\s+(?:some\s+)?focus\s+time",
            r"i\s+need\s+(?:some\s+)?focus\s+time",
            # Dutch
            r"blokkeer\s+(?:wat\s+)?focus\s+tijd",
            r"plan\s+focus\s+tijd",
            r"focus\s+tijd\s+nodig",
        ],
    }

    # Entity extraction patterns
    DATE_PATTERNS = [
        # English
        r"today",
        r"tomorrow",
        r"next\s+week",
        r"this\s+week",
        r"next\s+month",
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday",
        r"january|february|march|april|may|june|july|august|september|october|november|december",
        r"\d{1,2}(?:st|nd|rd|th)?",  # 15th, 1st, etc.
        # Dutch
        r"vandaag",
        r"morgen",
        r"overmorgen",
        r"gisteren",
        r"volgende\s+week",
        r"komende\s+week",
        r"maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag",
        r"januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december",
    ]

    TIME_PATTERNS = [
        # English numeric
        r"(\d{1,2}):(\d{2})\s*(am|pm)?",
        r"(\d{1,2})\s*(am|pm)",
        # English descriptive
        r"morning",
        r"afternoon",
        r"evening",
        r"lunch(?:time)?",
        r"after\s+lunch",
        r"before\s+lunch",
        r"end\s+of\s+day",
        r"start\s+of\s+day",
        # Dutch
        r"ochtend",
        r"morgenochtend",
        r"middag",
        r"vanmiddag",
        r"namiddag",
        r"avond",
        r"nacht",
        r"(\d{1,2})\s*uur",
        r"(\d{1,2}):(\d{2})\s*uur",
        r"lunch(?:tijd)?",
    ]

    DURATION_PATTERNS = [
        # English
        (r"(\d+)\s*minutes?", 1),
        (r"(\d+)\s*mins?", 1),
        (r"(\d+)\s*hours?", 60),
        (r"(\d+)\s*hrs?", 60),
        (r"half\s+an?\s+hour", 30),
        (r"one\s+hour", 60),
        (r"thirty\s+minutes", 30),
        (r"fifteen\s+minutes", 15),
        # Dutch
        (r"(\d+)\s*minuten?", 1),
        (r"(\d+)\s*min", 1),
        (r"(\d+)\s*uur", 60),
        (r"half\s+uur", 30),
        (r"een\s+uur", 60),
        (r"dertig\s+minuten", 30),
        (r"kwartier", 15),
    ]

    def __init__(self, db: AsyncSession | None = None) -> None:
        """Initialize the parser with compiled patterns."""
        self.db = db
        self.compiled_intent_patterns = {
            intent: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for intent, patterns in self.INTENT_PATTERNS.items()
        }
        self.reference_resolver = ReferenceResolver(db)
        self.dutch_normalizer = DutchDateNormalizer()

    async def parse(self, transcript: str, context: VoiceContext) -> VoiceIntent:
        """
        Parse voice transcript into structured intent.

        Args:
            transcript: The speech-to-text result
            context: Voice interaction context

        Returns:
            VoiceIntent with extracted entities
        """
        transcript_lower = transcript.lower().strip()

        # Classify intent
        intent_type, confidence = self._classify_intent(transcript_lower)

        # Extract entities
        participants = self._extract_participants(transcript_lower)
        date_expr = self._extract_date_expression(transcript_lower)
        time_expr = self._extract_time_expression(transcript_lower)
        duration = self._extract_duration(transcript_lower)
        title = self._extract_meeting_title(transcript_lower)

        # Try to resolve reference (e.g., "de 1-op-1 met de CTO")
        event_reference = None
        if self.db and any(word in transcript_lower for word in ["de", "het", "the", "my"]):
            event_reference = await self.reference_resolver.resolve_event_reference(
                transcript, context.user_id, context.tenant_id
            )

        return VoiceIntent(
            intent_type=intent_type,
            confidence=confidence,
            participants=participants,
            date_expression=date_expr,
            time_expression=time_expr,
            duration_minutes=duration,
            meeting_title=title,
            timezone=context.timezone,
            user_id=context.user_id,
            raw_transcript=transcript,
            event_id=event_reference.get("event_id") if event_reference else None,
        )

    def _classify_intent(self, transcript: str) -> tuple[VoiceIntentType, float]:
        """
        Classify the intent type from transcript.

        Returns:
            Tuple of (intent_type, confidence)
        """
        best_match = None
        best_score = 0.0

        for intent_type, patterns in self.compiled_intent_patterns.items():
            for pattern in patterns:
                match = pattern.search(transcript)
                if match:
                    # Calculate confidence based on match quality
                    score = len(match.group(0)) / len(transcript)
                    if score > best_score:
                        best_score = score
                        best_match = intent_type

        if best_match:
            # Boost confidence for exact matches
            confidence = min(0.9, 0.5 + best_score)
            return best_match, confidence

        # Check for cancellation keywords (English and Dutch)
        cancel_words = [
            "cancel",
            "delete",
            "remove",
            "annuleer",
            "verwijder",
            "afgelasten",
        ]
        if any(word in transcript for word in cancel_words):
            return VoiceIntentType.CANCEL_MEETING, 0.6

        # Check for reschedule keywords (English and Dutch)
        reschedule_words = [
            "move",
            "reschedule",
            "change",
            "verplaats",
            "verzet",
            "wijzig",
        ]
        if any(word in transcript for word in reschedule_words):
            return VoiceIntentType.RESCHEDULE_MEETING, 0.6

        # Check for availability keywords (English and Dutch)
        avail_words = ["available", "free", "when", "beschikbaar", "vrij", "wanneer"]
        if any(word in transcript for word in avail_words):
            return VoiceIntentType.CHECK_AVAILABILITY, 0.5

        return VoiceIntentType.UNKNOWN, 0.3

    def _extract_participants(self, transcript: str) -> list[str]:
        """Extract participant names from transcript (English and Dutch)."""
        participants = []

        # Pattern: "with [name]" or "and [name]" or Dutch "met [name]"
        with_pattern = re.compile(
            r"(?:with|and|met)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE
        )
        for match in with_pattern.finditer(transcript):
            name = match.group(1).strip()
            # Filter out common non-name words
            non_names = ["me", "i", "you", "the", "a", "een", "de", "het"]
            if name.lower() not in non_names:
                participants.append(name)

        # Pattern: "invite [name]" or Dutch "nodig [name] uit"
        invite_pattern = re.compile(r"(?:invite|nodig)\s+([A-Z][a-z]+)", re.IGNORECASE)
        for match in invite_pattern.finditer(transcript):
            participants.append(match.group(1))

        # Extract roles (CTO, CEO, etc.)
        role_pattern = re.compile(
            r"\b(CTO|CEO|CFO|COO|manager|director|lead|head)\b", re.IGNORECASE
        )
        for match in role_pattern.finditer(transcript):
            role = match.group(1)
            if role.lower() not in [p.lower() for p in participants]:
                participants.append(role)

        return list(set(participants))  # Remove duplicates

    def _extract_date_expression(self, transcript: str) -> str | None:
        """Extract date expression from transcript (English and Dutch)."""
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _extract_time_expression(self, transcript: str) -> str | None:
        """Extract time expression from transcript (English and Dutch)."""
        for pattern in self.TIME_PATTERNS:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _extract_duration(self, transcript: str) -> int | None:
        """Extract duration in minutes from transcript (English and Dutch)."""
        for pattern, multiplier in self.DURATION_PATTERNS:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                # Extract number if present
                try:
                    number = int(match.group(1))
                    return number * multiplier
                except (IndexError, ValueError):
                    # No number group, return the fixed value
                    return multiplier
        return None

    def _extract_meeting_title(self, transcript: str) -> str | None:
        """Extract meeting title from transcript (English and Dutch)."""
        # Pattern: "called [title]" or "about [topic]" or Dutch "genaamd [titel]"
        title_patterns = [
            r"called\s+['\"]?([^'\"]+)['\"]?",
            r"about\s+(['\"]?[^'\"]+['\"]?)",
            r"(?:regarding|re:)\s+(['\"]?[^'\"]+['\"]?)",
            r"(?:over|betreffende)\s+(['\"]?[^'\"]+['\"]?)",  # Dutch
            r"genaamd\s+(['\"]?[^'\"]+['\"]?)",  # Dutch
        ]

        for pattern in title_patterns:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                return match.group(1).strip('"')

        return None

    def parse_date_expression(self, expr: str, tz: str = "UTC") -> datetime | None:
        """
        Parse a date expression into an actual datetime.

        Supports both English and Dutch date expressions.
        """
        expr_lower = expr.lower()
        now = datetime.now(timezone.utc)

        # First try Dutch normalization
        dutch_date, dutch_time = self.dutch_normalizer.normalize(expr)
        if dutch_date:
            # Combine date and time
            if dutch_time:
                return dutch_date.replace(
                    hour=dutch_time.hour,
                    minute=dutch_time.minute,
                    second=0,
                    microsecond=0,
                )
            return dutch_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # English expressions
        if expr_lower == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)

        if expr_lower == "tomorrow":
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        if expr_lower == "next week":
            # Start of next week (Monday)
            days_until_monday = 7 - now.weekday()
            return (now + timedelta(days=days_until_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        # Weekday names (English)
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        if expr_lower in weekdays:
            target_day = weekdays[expr_lower]
            current_day = now.weekday()
            days_ahead = (target_day - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week if today
            return (now + timedelta(days=days_ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        return None

    def parse_time_expression(self, expr: str) -> time | None:
        """
        Parse a time expression into a time object.

        Supports both English and Dutch time expressions.
        """
        expr_lower = expr.lower()

        # First try Dutch normalization
        _, dutch_time = self.dutch_normalizer.normalize(expr)
        if dutch_time:
            return dutch_time

        # English morning, afternoon, evening
        if "morning" in expr_lower:
            return time(9, 0)
        if "afternoon" in expr_lower:
            return time(14, 0)
        if "evening" in expr_lower:
            return time(18, 0)
        if "lunch" in expr_lower:
            return time(12, 0)
        if "end of day" in expr_lower:
            return time(17, 0)
        if "start of day" in expr_lower:
            return time(9, 0)

        # Numeric times like "3pm", "15:00"
        match = re.match(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", expr_lower)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            period = match.group(3)

            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            return time(hour, minute)

        return None

    def resolve_relative_date(
        self, date_expr: str, time_expr: str, tz: str = "UTC"
    ) -> datetime | None:
        """
        Resolve a relative date/time expression to a concrete datetime.

        Example:
            - "vanmiddag" + "middag" -> today at 14:00
            - "morgenochtend" -> tomorrow at 09:00
        """
        date = self.parse_date_expression(date_expr, tz)
        time_obj = self.parse_time_expression(time_expr)

        if date and time_obj:
            return date.replace(hour=time_obj.hour, minute=time_obj.minute)
        elif date:
            return date
        elif time_obj:
            # Default to today if only time specified
            now = datetime.now(timezone.utc)
            return now.replace(hour=time_obj.hour, minute=time_obj.minute)

        return None
