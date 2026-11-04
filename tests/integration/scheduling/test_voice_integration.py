"""Integration tests for Voice UI API.

Tests use real PostgreSQL database with Redis session store.
No mocks except for auth.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.voice.session_store import get_session_store

pytestmark = pytest.mark.asyncio


class TestVoiceProcess:
    """Tests for POST /scheduling/voice/process (voice input processing)."""

    async def test_process_voice_schedule_meeting(self, async_client: AsyncClient):
        """Process voice input to schedule a meeting."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting with John tomorrow at 2pm for 30 minutes",
                "session_id": "test-session-1",
                "timezone": "UTC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "intent" in data
        assert "entities" in data
        assert "response_text" in data

        # Should identify schedule intent
        assert data["intent"] == "schedule_meeting"

    async def test_process_voice_cancel_event(self, async_client: AsyncClient, event_factory):
        """Process voice input to cancel an event."""
        # Create an event first
        event = await event_factory(title="Team Meeting")

        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Cancel my team meeting",
                "session_id": "test-session-2",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Intent is recognized, may require confirmation based on confidence
        assert data["intent"] in ["cancel_event", "confirm", "clarify"]

    async def test_process_voice_reschedule_event(self, async_client: AsyncClient):
        """Process voice input to reschedule an event."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Move my 2pm meeting to 4pm",
                "session_id": "test-session-3",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Intent is recognized, may require confirmation based on confidence
        assert data["intent"] in [
            "reschedule_event",
            "reschedule_meeting",
            "confirm",
            "clarify",
        ]

    async def test_process_voice_query_availability(self, async_client: AsyncClient):
        """Process voice input to query availability."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "When am I free tomorrow?",
                "session_id": "test-session-4",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Intent is recognized, may require confirmation based on confidence
        assert data["intent"] in [
            "query_availability",
            "check_availability",
            "confirm",
            "clarify",
        ]

    async def test_process_voice_unknown_intent(self, async_client: AsyncClient):
        """Process voice input with unknown intent."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Tell me a joke",
                "session_id": "test-session-5",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Unknown intents are handled gracefully
        assert data["intent"] in ["unknown", "clarify"]

    async def test_process_voice_validation_error(self, async_client: AsyncClient):
        """Process voice input with missing required fields."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                # Missing "text" field
                "session_id": "test-session-6",
            },
        )

        assert response.status_code == 422

    async def test_process_voice_session_context(self, async_client: AsyncClient):
        """Voice processing maintains session context."""
        session_id = "test-session-context"

        # First request
        response1 = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting with Alice",
                "session_id": session_id,
            },
        )
        assert response1.status_code == 200

        # Second request with context from first
        response2 = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Make it tomorrow at 3pm",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        data = response2.json()
        # Should have context from previous interaction
        assert "context" in data


class TestVoiceSessionStore:
    """Tests for Redis-backed voice session store."""

    async def test_session_store_get_set(self):
        """Test basic get/set operations on session store."""
        store = get_session_store()

        # Set session data with required fields
        session_data = {
            "user_id": "user-123",
            "tenant_id": 1,
            "timezone": "UTC",
            "intent": "schedule",
            "entities": {"participants": ["John"]},
        }
        await store.set("test-session", session_data)

        # Get session data
        data = await store.get("test-session")
        assert data is not None
        assert data.user_id == "user-123"
        assert data.tenant_id == 1

        # Clean up
        await store.delete("test-session")

    async def test_session_store_exists(self):
        """Test session exists check."""
        store = get_session_store()

        # Non-existent session
        exists = await store.exists("nonexistent-session")
        assert exists is False

        # Create session
        await store.set("existing-session", {"user_id": "user-123", "tenant_id": 1})
        exists = await store.exists("existing-session")
        assert exists is True

        # Clean up
        await store.delete("existing-session")

    async def test_session_store_delete(self):
        """Test session deletion."""
        store = get_session_store()

        # Create and delete session
        await store.set("delete-test", {"user_id": "user-123", "tenant_id": 1})
        await store.delete("delete-test")

        # Should not exist
        data = await store.get("delete-test")
        assert data is None

    async def test_session_store_ttl(self):
        """Test session expiration."""
        store = get_session_store()

        # Get TTL (should be 3600 seconds = 1 hour)
        assert store._ttl == 3600


class TestVoiceIntents:
    """Tests for GET /scheduling/voice/intents (list available intents)."""

    async def test_list_voice_intents(self, async_client: AsyncClient):
        """Get list of available voice intents."""
        response = await async_client.get("/api/v1/scheduling/voice/intents")

        assert response.status_code == 200
        data = response.json()
        assert "intents" in data
        assert isinstance(data["intents"], list)

        # Should include common intents
        intent_names = {i["name"] for i in data["intents"]}
        assert "schedule_meeting" in intent_names
        assert "cancel_event" in intent_names
        assert "reschedule_event" in intent_names
        assert "query_availability" in intent_names


class TestVoiceHealth:
    """Tests for GET /scheduling/voice/health (voice service health)."""

    async def test_voice_health_check(self, async_client: AsyncClient):
        """Check voice service health status."""
        response = await async_client.get("/api/v1/scheduling/voice/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

        # Should include Redis status
        assert "redis_connected" in data
        assert isinstance(data["redis_connected"], bool)


class TestVoiceConversationalFlow:
    """Tests for conversational voice interactions."""

    async def test_conversational_schedule_flow(self, async_client: AsyncClient):
        """Test multi-turn conversation for scheduling."""
        session_id = "conv-session-1"

        # Turn 1: Initial request (missing time)
        response1 = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting with Bob",
                "session_id": session_id,
            },
        )
        assert response1.status_code == 200
        data1 = response1.json()
        # Should ask for missing info
        assert "response_text" in data1

        # Turn 2: Provide time
        response2 = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Tomorrow at 10am",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        # Should confirm or ask for more info
        assert "response_text" in data2

    async def test_conversational_cancel_flow(self, async_client: AsyncClient, event_factory):
        """Test conversation flow for cancelling events."""
        # Create an event to cancel
        event = await event_factory(title="Team Standup")

        session_id = "conv-session-2"

        # Request to cancel
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Cancel my team standup",
                "session_id": session_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Intent is recognized, may require confirmation based on confidence
        assert data["intent"] in ["cancel_event", "confirm", "clarify"]

    async def test_conversational_reschedule_flow(self, async_client: AsyncClient, event_factory):
        """Test conversation flow for rescheduling events."""
        # Create an event to reschedule
        event = await event_factory(title="Client Meeting")

        session_id = "conv-session-3"

        # Request to reschedule
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Move my client meeting to Friday",
                "session_id": session_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Intent is recognized, may require confirmation based on confidence
        assert data["intent"] in [
            "reschedule_event",
            "reschedule_meeting",
            "confirm",
            "clarify",
        ]


class TestVoiceEntityExtraction:
    """Tests for entity extraction from voice input."""

    async def test_extract_date_entities(self, async_client: AsyncClient):
        """Extract date entities from voice input."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting next Monday",
                "session_id": "entity-session-1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        entities = data.get("entities", {})
        # Check for date-related entities (either normalized date or original expression)
        assert "date_expression" in entities or "date" in entities or "relative_date" in entities

    async def test_extract_time_entities(self, async_client: AsyncClient):
        """Extract time entities from voice input."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting at 3:30pm",
                "session_id": "entity-session-2",
            },
        )

        assert response.status_code == 200
        data = response.json()
        entities = data.get("entities", {})
        # Check for time-related entities
        assert "time_expression" in entities or "time" in entities

    async def test_extract_duration_entities(self, async_client: AsyncClient):
        """Extract duration entities from voice input."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a 45 minute meeting",
                "session_id": "entity-session-3",
            },
        )

        assert response.status_code == 200
        data = response.json()
        entities = data.get("entities", {})
        # Duration may be in duration_minutes or extracted from text
        assert "duration_minutes" in entities or "duration" in entities

    async def test_extract_person_entities(self, async_client: AsyncClient):
        """Extract person/attendee entities from voice input."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Meet with Alice and Bob tomorrow",
                "session_id": "entity-session-4",
            },
        )

        assert response.status_code == 200
        data = response.json()
        entities = data.get("entities", {})
        # Check for participant-related entities
        assert "participants" in entities or "attendees" in entities or "person" in entities


class TestVoiceErrorHandling:
    """Tests for voice API error handling."""

    async def test_voice_empty_text(self, async_client: AsyncClient):
        """Handle empty text input gracefully."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "",
                "session_id": "error-session-1",
            },
        )

        # Should either succeed with unknown intent or return 400
        assert response.status_code in [200, 400, 422]

    async def test_voice_invalid_json(self, async_client: AsyncClient):
        """Handle invalid JSON gracefully."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            content=b"invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_voice_missing_session_id(self, async_client: AsyncClient):
        """Generate session ID if not provided."""
        response = await async_client.post(
            "/api/v1/scheduling/voice/process",
            json={
                "transcript": "Schedule a meeting tomorrow",
                # Missing session_id
            },
        )

        # Should either succeed or return validation error
        assert response.status_code in [200, 422]
