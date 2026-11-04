"""Integration tests for Dutch language voice scheduling.

Tests Use-Case 1: Executive Assistant - Meeting Rescheduling via Voice
Example: "Verplaats de 1-op-1 met de CTO van vanmiddag naar morgenochtend"
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.voice.intents import VoiceContext
from src.core.scheduling.voice.nlu import DutchDateNormalizer, VoiceIntentParser

pytestmark = pytest.mark.asyncio


class TestDutchDateNormalization:
    """Tests for Dutch date/time normalization."""

    async def test_dutch_relative_dates(self):
        """Normalize Dutch relative dates."""
        normalizer = DutchDateNormalizer()

        # Test vandaag (today)
        date, time = normalizer.normalize("vandaag")
        assert date is not None

        # Test morgen (tomorrow)
        date, time = normalizer.normalize("morgen")
        assert date is not None

        # Test overmorgen (day after tomorrow)
        date, time = normalizer.normalize("overmorgen")
        assert date is not None

    async def test_dutch_time_periods(self):
        """Normalize Dutch time periods."""
        normalizer = DutchDateNormalizer()

        # Test ochtend (morning)
        date, time = normalizer.normalize("ochtend")
        assert time is not None
        assert time.hour == 9

        # Test middag (afternoon)
        date, time = normalizer.normalize("middag")
        assert time is not None
        assert time.hour == 14

        # Test vanmiddag (this afternoon)
        date, time = normalizer.normalize("vanmiddag")
        assert time is not None
        assert time.hour == 14

        # Test morgenochtend (tomorrow morning)
        date, time = normalizer.normalize("morgenochtend")
        assert date is not None
        assert time is not None
        assert time.hour == 9

    async def test_dutch_weekdays(self):
        """Normalize Dutch weekdays."""
        normalizer = DutchDateNormalizer()

        weekdays = [
            "maandag",
            "dinsdag",
            "woensdag",
            "donderdag",
            "vrijdag",
            "zaterdag",
            "zondag",
        ]
        for day in weekdays:
            date, time = normalizer.normalize(day)
            assert date is not None, f"Failed to normalize {day}"


class TestDutchIntentRecognition:
    """Tests for Dutch intent recognition."""

    async def test_dutch_reschedule_intent(self):
        """Recognize Dutch reschedule intent."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        # Test "verplaats" (reschedule/move)
        result = await parser.parse("Verplaats de meeting naar morgen", context)
        assert result.intent_type.value == "reschedule_meeting"
        assert result.confidence > 0.5

        # Test "verzet" (reschedule)
        result = await parser.parse("Verzet de afspraak naar volgende week", context)
        assert result.intent_type.value == "reschedule_meeting"

        # Test "wijzig" (change)
        result = await parser.parse("Wijzig de vergadering", context)
        assert result.intent_type.value == "reschedule_meeting"

    async def test_dutch_cancel_intent(self):
        """Recognize Dutch cancel intent."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        # Test "annuleer" (cancel)
        result = await parser.parse("Annuleer de meeting", context)
        assert result.intent_type.value == "cancel_meeting"

        # Test "afgelasten"
        result = await parser.parse("Ik wil de vergadering afgelasten", context)
        assert result.intent_type.value == "cancel_meeting"

    async def test_dutch_schedule_intent(self):
        """Recognize Dutch schedule intent."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        # Test "plan" (schedule)
        result = await parser.parse("Plan een afspraak met John", context)
        assert result.intent_type.value == "schedule_meeting"

        # Test "maak" (create)
        result = await parser.parse("Maak een vergadering voor morgen", context)
        assert result.intent_type.value == "schedule_meeting"


class TestDutchEntityExtraction:
    """Tests for Dutch entity extraction."""

    async def test_dutch_participant_extraction(self):
        """Extract participants from Dutch transcript."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        # Test "met" (with)
        result = await parser.parse("Plan een meeting met Alice", context)
        assert any("alice" in p.lower() for p in result.participants)

        # Test multiple participants
        result = await parser.parse("Vergader met Bob en Charlie", context)
        assert any("bob" in p.lower() for p in result.participants)

    async def test_dutch_role_extraction(self):
        """Extract roles (CTO, CEO) from Dutch transcript."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        # Test CTO role
        result = await parser.parse("Verplaats de 1-op-1 met de CTO", context)
        assert any("cto" in p.lower() for p in result.participants)

        # Test CEO role
        result = await parser.parse("Plan een meeting met de CEO", context)
        assert any("ceo" in p.lower() for p in result.participants)

    async def test_dutch_date_extraction(self):
        """Extract date expressions from Dutch transcript."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        result = await parser.parse("Plan een meeting morgen", context)
        assert result.date_expression is not None

        result = await parser.parse("Vergader volgende week", context)
        assert result.date_expression is not None

    async def test_dutch_time_extraction(self):
        """Extract time expressions from Dutch transcript."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        result = await parser.parse("Plan een meeting vanmiddag", context)
        assert result.time_expression is not None

        result = await parser.parse("Vergader om 14 uur", context)
        assert result.time_expression is not None

    async def test_dutch_duration_extraction(self):
        """Extract duration from Dutch transcript."""
        parser = VoiceIntentParser()
        context = VoiceContext(user_id="test-user", tenant_id=1)

        result = await parser.parse("Plan een meeting van een uur", context)
        assert result.duration_minutes == 60

        result = await parser.parse("Vergader voor dertig minuten", context)
        assert result.duration_minutes == 30

        result = await parser.parse("Een kwartier meeting", context)
        assert result.duration_minutes == 15


class TestDutchEndToEnd:
    """End-to-end tests for Dutch voice scheduling."""

    async def test_dutch_reschedule_via_api(self, async_client: AsyncClient, event_factory):
        """Test Dutch reschedule via API."""
        # Create an event first
        event = await event_factory(title="1-op-1 met de CTO")

        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Verplaats de 1-op-1 met de CTO van vanmiddag naar morgenochtend",
                "session_id": "dutch-session-1",
                "timezone": "UTC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should identify reschedule intent or ask for confirmation
        assert data["intent"] in ["reschedule_meeting", "confirm", "clarify"]

    async def test_dutch_schedule_via_api(self, async_client: AsyncClient):
        """Test Dutch schedule via API."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Plan een meeting met John morgenmiddag voor een uur",
                "session_id": "dutch-session-2",
                "timezone": "UTC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should identify schedule intent or ask for confirmation
        assert data["intent"] in ["schedule_meeting", "confirm", "clarify"]

    async def test_dutch_cancel_via_api(self, async_client: AsyncClient, event_factory):
        """Test Dutch cancel via API."""
        # Create an event first
        event = await event_factory(title="Team vergadering")

        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Annuleer de team vergadering",
                "session_id": "dutch-session-3",
                "timezone": "UTC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should identify cancel intent or ask for confirmation
        assert data["intent"] in ["cancel_event", "confirm", "clarify"]


class TestReferenceResolution:
    """Tests for reference resolution (e.g., "de 1-op-1 met de CTO")."""

    async def test_reference_resolver_extract_keywords(self):
        """Test keyword extraction from references."""
        from src.core.scheduling.voice.nlu import ReferenceResolver

        resolver = ReferenceResolver()

        # Test meeting type extraction
        keywords = resolver._extract_reference_keywords("de 1-op-1 met de CTO")
        assert any("1-op-1" in k.lower() or "cto" in k.lower() for k in keywords)

        # Test role extraction
        keywords = resolver._extract_reference_keywords("meeting met de CEO")
        assert any("ceo" in k.lower() for k in keywords)

    async def test_reference_resolver_score(self):
        """Test scoring of event matches."""
        from unittest.mock import MagicMock

        from src.core.scheduling.voice.nlu import ReferenceResolver

        resolver = ReferenceResolver()

        # Create mock event
        event = MagicMock()
        event.title = "1-op-1 with CTO"
        event.description = None

        # Test matching
        score = resolver._calculate_match_score(event, ["1-op-1", "CTO"])
        assert score > 0
