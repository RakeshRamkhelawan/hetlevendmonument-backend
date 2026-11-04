"""Tests for the entity resolver module."""

from datetime import datetime, time, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.scheduling.voice.entity_resolver import (
    DateTimeResolver,
    MeetingResolver,
    PersonResolver,
)
from src.core.scheduling.voice.intents import VoiceContext


class TestDateTimeResolver:
    """Test suite for DateTimeResolver."""

    @pytest.fixture
    def reference_time(self) -> datetime:
        """Create a reference time for consistent testing."""
        return datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)  # Sunday

    def test_resolve_today_morning(self, reference_time: datetime) -> None:
        """Test resolving 'today morning' expression."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr="morning",
            reference_time=reference_time,
        )

        assert start_dt.date() == reference_time.date()
        assert start_dt.time() == time(8, 0)
        assert end_dt.time() == time(12, 0)

    def test_resolve_tomorrow_afternoon(self, reference_time: datetime) -> None:
        """Test resolving 'tomorrow afternoon' expression."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="tomorrow",
            time_expr="afternoon",
            reference_time=reference_time,
        )

        expected_date = (reference_time + __import__("datetime").timedelta(days=1)).date()
        assert start_dt.date() == expected_date
        assert start_dt.time() == time(12, 0)
        assert end_dt.time() == time(17, 0)

    def test_resolve_next_monday(self, reference_time: datetime) -> None:
        """Test resolving 'next Monday' (weekday navigation)."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="next monday",
            time_expr="morning",
            reference_time=reference_time,
        )

        # Reference is Sunday 2026-03-15. Next Monday is 2026-03-16 + 7 = 2026-03-23
        assert start_dt.weekday() == 0  # Monday
        assert start_dt.time() == time(8, 0)

    def test_resolve_explicit_time_2pm(self, reference_time: datetime) -> None:
        """Test resolving explicit time like '2pm'."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr="2pm",
            reference_time=reference_time,
        )

        assert start_dt.time() == time(14, 0)
        assert end_dt.time() == time(15, 0)

    def test_resolve_explicit_time_14_30(self, reference_time: datetime) -> None:
        """Test resolving explicit time like '14:30'."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr="14:30",
            reference_time=reference_time,
        )

        assert start_dt.time() == time(14, 30)
        assert end_dt.time() == time(15, 30)

    def test_resolve_dutch_morning(self, reference_time: datetime) -> None:
        """Test resolving Dutch 'morgenochtend' (tomorrow morning)."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr="morgenochtend",
            reference_time=reference_time,
        )

        assert start_dt.time() == time(8, 0)
        assert end_dt.time() == time(12, 0)

    def test_resolve_default_time_no_time_expr(self, reference_time: datetime) -> None:
        """Test default time when no time expression given."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr=None,
            reference_time=reference_time,
        )

        assert start_dt.time() == time(11, 0)
        assert end_dt.time() == time(12, 0)

    def test_resolve_default_fallback_time(self, reference_time: datetime) -> None:
        """Test default fallback when time expression is unrecognized."""
        start_dt, end_dt = DateTimeResolver.resolve_date_expression(
            date_expr="today",
            time_expr="unknown_time",
            reference_time=reference_time,
        )

        assert start_dt.time() == time(9, 0)
        assert end_dt.time() == time(10, 0)


class TestPersonResolver:
    """Test suite for PersonResolver."""

    @pytest.fixture
    def voice_context(self) -> VoiceContext:
        """Create a voice context for testing."""
        return VoiceContext(
            user_id="user_123",
            tenant_id=1,
            timezone="UTC",
        )

    @pytest.mark.asyncio
    async def test_resolve_role_cto(self, voice_context: VoiceContext) -> None:
        """Test resolving role reference 'CTO'."""
        # Currently returns None (TODO: implement DB lookup)
        result = await PersonResolver.resolve_person("CTO", voice_context)

        # TODO: Remove this assertion when DB lookup is implemented
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_role_manager(self, voice_context: VoiceContext) -> None:
        """Test resolving role reference 'manager'."""
        result = await PersonResolver.resolve_person("manager", voice_context)

        # TODO: Remove this assertion when DB lookup is implemented
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_name_pattern(self, voice_context: VoiceContext) -> None:
        """Test resolving name pattern 'John Smith'."""
        result = await PersonResolver.resolve_person("John Smith", voice_context)

        # TODO: Remove this assertion when DB lookup is implemented
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_with_db_session(self, voice_context: VoiceContext) -> None:
        """Test resolve_person with optional db_session parameter."""
        db_session = AsyncMock()
        result = await PersonResolver.resolve_person("Alex", voice_context, db_session)

        # TODO: Remove this assertion when DB lookup is implemented
        assert result is None


class TestMeetingResolver:
    """Test suite for MeetingResolver."""

    @pytest.fixture
    def voice_context(self) -> VoiceContext:
        """Create a voice context for testing."""
        return VoiceContext(
            user_id="user_123",
            tenant_id=1,
            timezone="UTC",
        )

    @pytest.mark.asyncio
    async def test_resolve_standup_meeting(self, voice_context: VoiceContext) -> None:
        """Test resolving standup meeting reference."""
        result = await MeetingResolver.resolve_meeting("the standup", voice_context)

        # Currently returns None (TODO: implement DB lookup)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_one_on_one(self, voice_context: VoiceContext) -> None:
        """Test resolving 1-on-1 meeting reference."""
        result = await MeetingResolver.resolve_meeting("the 1-on-1 with Alex", voice_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_meeting_with_person(self, voice_context: VoiceContext) -> None:
        """Test resolving meeting with person reference."""
        result = await MeetingResolver.resolve_meeting("meeting with John", voice_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_review_meeting(self, voice_context: VoiceContext) -> None:
        """Test resolving review/retrospective meeting."""
        result = await MeetingResolver.resolve_meeting("the retrospective", voice_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_with_db_session(self, voice_context: VoiceContext) -> None:
        """Test resolve_meeting with optional db_session parameter."""
        db_session = AsyncMock()
        result = await MeetingResolver.resolve_meeting("standup", voice_context, db_session)

        assert result is None

    def test_extract_standup_reference(self) -> None:
        """Test extracting standup from transcript."""
        transcript = "I need to schedule the standup with the team"
        result = MeetingResolver.extract_meeting_reference(transcript)

        assert result == "standup"

    def test_extract_one_on_one_reference(self) -> None:
        """Test extracting 1-on-1 from transcript."""
        transcript = "Let's reschedule the 1-on-1 with Sarah"
        result = MeetingResolver.extract_meeting_reference(transcript)

        assert result == "1-on-1 with Sarah"

    def test_extract_meeting_with_person_reference(self) -> None:
        """Test extracting meeting with person from transcript."""
        transcript = "I have a meeting with John at 2pm"
        result = MeetingResolver.extract_meeting_reference(transcript)

        assert result == "meeting with John at"

    def test_extract_no_meeting_reference(self) -> None:
        """Test extracting from transcript with no meeting reference."""
        transcript = "Let me check the calendar"
        result = MeetingResolver.extract_meeting_reference(transcript)

        assert result is None

    def test_extract_review_reference(self) -> None:
        """Test extracting review/retrospective from transcript."""
        transcript = "I want to block time for the sprint review"
        result = MeetingResolver.extract_meeting_reference(transcript)

        assert result == "review"
