"""
Unit tests for GoogleCalendarProvider.

Uses respx to mock httpx HTTP calls.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import Response

import respx
from src.core.scheduling.integrations.google_calendar import GoogleCalendarProvider


@pytest.fixture
def provider() -> GoogleCalendarProvider:
    """Create a provider with test credentials."""
    return GoogleCalendarProvider(
        client_id="test-client-id",
        client_secret="test-client-secret",
    )


class TestGoogleCalendarOAuth:
    """Tests for OAuth token exchange and refresh."""

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, provider: GoogleCalendarProvider) -> None:
        """Test successful OAuth code exchange."""

        @respx.mock
        async def inner_test():
            # Mock token endpoint
            token_url = "https://oauth2.googleapis.com/token"
            respx.post(token_url).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "new-access-token",
                        "refresh_token": "new-refresh-token",
                        "expires_in": 3600,
                        "scope": "https://www.googleapis.com/auth/calendar",
                    },
                )
            )

            # Mock userinfo endpoint
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            respx.get(userinfo_url).mock(
                return_value=Response(
                    200,
                    json={
                        "id": "user-123",
                        "email": "user@example.com",
                    },
                )
            )

            tokens = await provider.exchange_code(
                code="auth-code",
                redirect_uri="http://localhost/callback",
            )

            assert tokens.access_token == "new-access-token"
            assert tokens.refresh_token == "new-refresh-token"
            assert tokens.account_id == "user-123"
            assert tokens.scope == "https://www.googleapis.com/auth/calendar"
            assert tokens.expires_at is not None

        await inner_test()

    @pytest.mark.asyncio
    async def test_exchange_code_error(self, provider: GoogleCalendarProvider) -> None:
        """Test OAuth code exchange failure."""

        @respx.mock
        async def inner_test():
            token_url = "https://oauth2.googleapis.com/token"
            respx.post(token_url).mock(return_value=Response(400, json={"error": "invalid_grant"}))

            with pytest.raises(Exception):
                await provider.exchange_code(
                    code="invalid-code",
                    redirect_uri="http://localhost/callback",
                )

        await inner_test()

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, provider: GoogleCalendarProvider) -> None:
        """Test successful token refresh."""

        @respx.mock
        async def inner_test():
            token_url = "https://oauth2.googleapis.com/token"
            respx.post(token_url).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "refreshed-access-token",
                        "expires_in": 3600,
                        "scope": "https://www.googleapis.com/auth/calendar",
                    },
                )
            )

            tokens = await provider.refresh_access_token(refresh_token="old-refresh-token")

            assert tokens.access_token == "refreshed-access-token"
            assert tokens.refresh_token == "old-refresh-token"  # Preserved if not returned
            assert tokens.expires_at is not None

        await inner_test()


class TestGoogleCalendarEvents:
    """Tests for event CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_events_success(self, provider: GoogleCalendarProvider) -> None:
        """Test listing events from Google Calendar."""

        @respx.mock
        async def inner_test():
            events_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            respx.get(events_url).mock(
                return_value=Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": "event-1",
                                "summary": "Team Meeting",
                                "start": {"dateTime": "2026-03-20T10:00:00Z"},
                                "end": {"dateTime": "2026-03-20T11:00:00Z"},
                                "status": "confirmed",
                            }
                        ],
                        "nextSyncToken": "sync-token-123",
                    },
                )
            )

            time_min = datetime(2026, 3, 1, tzinfo=timezone.utc)
            time_max = datetime(2026, 3, 31, tzinfo=timezone.utc)

            events, sync_token = await provider.list_events(
                access_token="test-token",
                time_min=time_min,
                time_max=time_max,
            )

            assert len(events) == 1
            assert events[0].external_id == "event-1"
            assert events[0].title == "Team Meeting"
            assert sync_token == "sync-token-123"

        await inner_test()

    @pytest.mark.asyncio
    async def test_list_events_with_sync_token(self, provider: GoogleCalendarProvider) -> None:
        """Test incremental sync using sync token."""

        @respx.mock
        async def inner_test():
            events_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            respx.get(events_url).mock(
                return_value=Response(
                    200,
                    json={
                        "items": [],
                        "nextSyncToken": "new-sync-token-456",
                    },
                )
            )

            time_min = datetime(2026, 3, 1, tzinfo=timezone.utc)
            time_max = datetime(2026, 3, 31, tzinfo=timezone.utc)

            events, sync_token = await provider.list_events(
                access_token="test-token",
                time_min=time_min,
                time_max=time_max,
                sync_token="old-sync-token",
            )

            assert len(events) == 0
            assert sync_token == "new-sync-token-456"

        await inner_test()

    @pytest.mark.asyncio
    async def test_list_events_all_day(self, provider: GoogleCalendarProvider) -> None:
        """Test parsing all-day events."""

        @respx.mock
        async def inner_test():
            events_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            respx.get(events_url).mock(
                return_value=Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": "event-2",
                                "summary": "Holiday",
                                "start": {"date": "2026-03-20"},
                                "end": {"date": "2026-03-21"},
                                "status": "confirmed",
                            }
                        ],
                    },
                )
            )

            time_min = datetime(2026, 3, 1, tzinfo=timezone.utc)
            time_max = datetime(2026, 3, 31, tzinfo=timezone.utc)

            events, _ = await provider.list_events(
                access_token="test-token",
                time_min=time_min,
                time_max=time_max,
            )

            assert len(events) == 1
            assert events[0].is_all_day is True
            assert events[0].title == "Holiday"

        await inner_test()

    @pytest.mark.asyncio
    async def test_create_event_success(self, provider: GoogleCalendarProvider) -> None:
        """Test creating an event on Google Calendar."""

        @respx.mock
        async def inner_test():
            events_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            respx.post(events_url).mock(
                return_value=Response(
                    200,
                    json={"id": "new-event-id"},
                )
            )

            from src.core.scheduling.integrations.base_provider import ExternalEvent

            event = ExternalEvent(
                external_id="",
                title="New Meeting",
                start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
                description="Test description",
                location="Conference Room A",
            )

            event_id = await provider.create_event(
                access_token="test-token",
                event=event,
            )

            assert event_id == "new-event-id"

        await inner_test()

    @pytest.mark.asyncio
    async def test_update_event_success(self, provider: GoogleCalendarProvider) -> None:
        """Test updating an event on Google Calendar."""

        @respx.mock
        async def inner_test():
            event_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events/event-123"
            respx.put(event_url).mock(return_value=Response(200, json={}))

            from src.core.scheduling.integrations.base_provider import ExternalEvent

            event = ExternalEvent(
                external_id="event-123",
                title="Updated Meeting",
                start_time=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 3, 20, 15, 0, tzinfo=timezone.utc),
            )

            await provider.update_event(
                access_token="test-token",
                external_id="event-123",
                event=event,
            )

        await inner_test()

    @pytest.mark.asyncio
    async def test_delete_event_success(self, provider: GoogleCalendarProvider) -> None:
        """Test deleting an event from Google Calendar."""

        @respx.mock
        async def inner_test():
            event_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events/event-123"
            respx.delete(event_url).mock(return_value=Response(204))

            await provider.delete_event(
                access_token="test-token",
                external_id="event-123",
            )

        await inner_test()

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, provider: GoogleCalendarProvider) -> None:
        """Test fetching user info."""

        @respx.mock
        async def inner_test():
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            respx.get(userinfo_url).mock(
                return_value=Response(
                    200,
                    json={
                        "id": "user-123",
                        "email": "user@example.com",
                    },
                )
            )

            user_info = await provider.get_user_info(access_token="test-token")

            assert user_info["id"] == "user-123"
            assert user_info["email"] == "user@example.com"

        await inner_test()


class TestGoogleCalendarEventParsing:
    """Tests for event parsing edge cases."""

    def test_parse_event_with_attendees(self, provider: GoogleCalendarProvider) -> None:
        """Test parsing events with attendees."""
        item = {
            "id": "event-3",
            "summary": "Meeting with Attendees",
            "start": {"dateTime": "2026-03-20T10:00:00Z"},
            "end": {"dateTime": "2026-03-20T11:00:00Z"},
            "attendees": [
                {"email": "attendee1@example.com"},
                {"email": "attendee2@example.com"},
            ],
        }

        event = provider._parse_event(item)

        assert event.attendees == ["attendee1@example.com", "attendee2@example.com"]

    def test_parse_event_no_title(self, provider: GoogleCalendarProvider) -> None:
        """Test parsing event without title."""
        item = {
            "id": "event-4",
            "start": {"dateTime": "2026-03-20T10:00:00Z"},
            "end": {"dateTime": "2026-03-20T11:00:00Z"},
        }

        event = provider._parse_event(item)

        assert event.title == "(no title)"

    def test_build_event_body_complete(self, provider: GoogleCalendarProvider) -> None:
        """Test building event body with all fields."""
        from src.core.scheduling.integrations.base_provider import ExternalEvent

        event = ExternalEvent(
            external_id="",
            title="Test Meeting",
            start_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
            description="Test description",
            location="Room A",
            attendees=["user1@example.com", "user2@example.com"],
        )

        body = provider._build_event_body(event)

        assert body["summary"] == "Test Meeting"
        assert body["description"] == "Test description"
        assert body["location"] == "Room A"
        assert len(body["attendees"]) == 2
