"""Unit tests for conflict detection, slot finder, and scheduling service.

Uses an in-memory SQLite database via async engine so the repository
layer works without mocks.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database.database import Base
from src.core.models.rbac_models import Tenant  # noqa: F401 - registers FK target
from src.core.scheduling.models import CalendarEvent, SchedulingPreference, TimeBlock
from src.core.scheduling.repository import (
    CalendarEventRepository,
    PreferenceRepository,
    TimeBlockRepository,
)
from src.core.scheduling.schemas import CalendarEventCreate, CalendarEventUpdate, SchedulingRequest
from src.core.scheduling.services.conflict_service import ConflictDetectionService
from src.core.scheduling.services.scheduling_service import SchedulingError, SchedulingService
from src.core.scheduling.services.slot_finder import SlotFinder

TENANT_ID = 99
ORGANIZER = "user-org"
PARTICIPANT = "user-part"


@pytest_asyncio.fixture
async def db_session():
    """Provide a fresh async session backed by in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:sched_test?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


# -------------------------------------------------------------------------
# ConflictDetectionService tests
# -------------------------------------------------------------------------


class TestConflictDetectionService:
    """Tests for SQL-based conflict detection."""

    @pytest.mark.asyncio
    async def test_no_conflicts_when_empty(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)
        svc = ConflictDetectionService(event_repo, block_repo)

        start = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

        conflicts = await svc.check_conflicts(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[PARTICIPANT],
            start=start,
            end=end,
        )
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_detects_organizer_overlap(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)

        existing = CalendarEvent(
            tenant_id=TENANT_ID,
            title="Existing meeting",
            start_time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc),
            organizer_id=ORGANIZER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        await event_repo.create(existing)

        svc = ConflictDetectionService(event_repo, block_repo)
        conflicts = await svc.check_conflicts(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[],
            start=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
            end=datetime(2025, 6, 15, 11, 30, tzinfo=timezone.utc),
        )
        assert len(conflicts) == 1
        assert conflicts[0].severity == "hard"
        assert conflicts[0].title == "Existing meeting"

    @pytest.mark.asyncio
    async def test_hard_block_creates_conflict(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)

        block = TimeBlock(
            tenant_id=TENANT_ID,
            user_id=ORGANIZER,
            block_type="focus_time",
            start_time=datetime(2025, 6, 15, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 15, 16, 0, tzinfo=timezone.utc),
            is_hard_block=True,
            label="Deep work",
        )
        await block_repo.create(block)

        svc = ConflictDetectionService(event_repo, block_repo)
        conflicts = await svc.check_conflicts(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[],
            start=datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc),
            end=datetime(2025, 6, 15, 15, 30, tzinfo=timezone.utc),
        )
        assert len(conflicts) == 1
        assert conflicts[0].severity == "hard"
        assert "Deep work" in conflicts[0].title

    @pytest.mark.asyncio
    async def test_has_hard_conflicts_boolean(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)
        svc = ConflictDetectionService(event_repo, block_repo)

        start = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

        result = await svc.has_hard_conflicts(TENANT_ID, ORGANIZER, [], start, end)
        assert result is False

    @pytest.mark.asyncio
    async def test_exclude_event_id(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)

        existing = CalendarEvent(
            tenant_id=TENANT_ID,
            title="Self",
            start_time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc),
            organizer_id=ORGANIZER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        created = await event_repo.create(existing)

        svc = ConflictDetectionService(event_repo, block_repo)
        conflicts = await svc.check_conflicts(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[],
            start=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc),
            end=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc),
            exclude_event_id=created.id,
        )
        assert len(conflicts) == 0


# -------------------------------------------------------------------------
# SlotFinder tests
# -------------------------------------------------------------------------


class TestSlotFinder:
    """Tests for the slot finding algorithm."""

    @pytest.mark.asyncio
    async def test_finds_slots_in_empty_calendar(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)
        pref_repo = PreferenceRepository(db_session)
        conflict_svc = ConflictDetectionService(event_repo, block_repo)
        finder = SlotFinder(conflict_svc, pref_repo)

        start = datetime(2025, 6, 16, 8, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 16, 18, 0, tzinfo=timezone.utc)

        options = await finder.find_slots(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[PARTICIPANT],
            duration_minutes=30,
            earliest_start=start,
            latest_end=end,
        )
        assert len(options) > 0
        # Best options should be during working hours
        for opt in options:
            assert 0.0 <= opt.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_working_hours_scored_higher(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)
        pref_repo = PreferenceRepository(db_session)
        conflict_svc = ConflictDetectionService(event_repo, block_repo)
        finder = SlotFinder(conflict_svc, pref_repo)

        # Window spans 6AM-10AM: 6-9 outside working hours, 9-10 inside
        start = datetime(2025, 6, 16, 6, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 16, 10, 30, tzinfo=timezone.utc)

        options = await finder.find_slots(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[PARTICIPANT],
            duration_minutes=30,
            earliest_start=start,
            latest_end=end,
        )
        assert len(options) > 0
        # First option (highest score) should be during working hours (9-10)
        best = options[0]
        assert best.confidence_score > 0.1  # higher than off-hours

    @pytest.mark.asyncio
    async def test_respects_user_preferences(self, db_session):
        event_repo = CalendarEventRepository(db_session)
        block_repo = TimeBlockRepository(db_session)
        pref_repo = PreferenceRepository(db_session)

        pref = SchedulingPreference(
            tenant_id=TENANT_ID,
            user_id=ORGANIZER,
            timezone_name="UTC",
            working_hours_start="10:00",
            working_hours_end="14:00",
            preferred_duration_minutes=30,
            buffer_minutes=10,
        )
        await pref_repo.upsert(pref)

        conflict_svc = ConflictDetectionService(event_repo, block_repo)
        finder = SlotFinder(conflict_svc, pref_repo)

        start = datetime(2025, 6, 16, 8, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 16, 16, 0, tzinfo=timezone.utc)

        options = await finder.find_slots(
            tenant_id=TENANT_ID,
            organizer_id=ORGANIZER,
            participant_ids=[PARTICIPANT],
            duration_minutes=30,
            earliest_start=start,
            latest_end=end,
        )
        best = options[0]
        # Best slot should be between 10:00 and 14:00
        assert 10 <= best.start_time.hour < 14


# -------------------------------------------------------------------------
# SchedulingService tests
# -------------------------------------------------------------------------


class TestSchedulingService:
    """Tests for the orchestration service."""

    @pytest.mark.asyncio
    async def test_schedule_meeting_success(self, db_session):
        svc = SchedulingService(db_session)

        request = SchedulingRequest(
            title="Sprint Planning",
            duration_minutes=60,
            participants=[PARTICIPANT],
            earliest_start=datetime(2025, 6, 16, 9, 0, tzinfo=timezone.utc),
            latest_end=datetime(2025, 6, 16, 17, 0, tzinfo=timezone.utc),
        )
        result = await svc.schedule_meeting(
            request=request,
            organizer_id=ORGANIZER,
            tenant_id=TENANT_ID,
        )
        assert result.success is True
        assert result.event_id is not None
        assert result.selected_option is not None
        assert result.message == "Meeting scheduled successfully."

    @pytest.mark.asyncio
    async def test_schedule_meeting_no_slots(self, db_session):
        svc = SchedulingService(db_session)

        # Tiny window that can't fit the duration
        start = datetime(2025, 6, 16, 9, 0, tzinfo=timezone.utc)
        request = SchedulingRequest(
            title="Impossible",
            duration_minutes=120,
            participants=[PARTICIPANT],
            earliest_start=start,
            latest_end=start + timedelta(minutes=30),
        )
        result = await svc.schedule_meeting(
            request=request,
            organizer_id=ORGANIZER,
            tenant_id=TENANT_ID,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_create_event(self, db_session):
        svc = SchedulingService(db_session)
        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)

        data = CalendarEventCreate(
            title="1:1",
            start_time=now,
            end_time=now + timedelta(minutes=30),
        )
        event = await svc.create_event(data, ORGANIZER, TENANT_ID)
        assert event.id is not None
        assert event.title == "1:1"

    @pytest.mark.asyncio
    async def test_get_event(self, db_session):
        svc = SchedulingService(db_session)
        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        data = CalendarEventCreate(
            title="Get me",
            start_time=now,
            end_time=now + timedelta(minutes=30),
        )
        created = await svc.create_event(data, ORGANIZER, TENANT_ID)

        fetched = await svc.get_event(created.id, TENANT_ID)
        assert fetched is not None
        assert fetched.title == "Get me"

    @pytest.mark.asyncio
    async def test_get_event_wrong_tenant(self, db_session):
        svc = SchedulingService(db_session)
        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        data = CalendarEventCreate(
            title="Scoped",
            start_time=now,
            end_time=now + timedelta(minutes=30),
        )
        created = await svc.create_event(data, ORGANIZER, TENANT_ID)

        # Different tenant should NOT see the event
        fetched = await svc.get_event(created.id, TENANT_ID + 1)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_update_event(self, db_session):
        svc = SchedulingService(db_session)
        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        data = CalendarEventCreate(
            title="Original",
            start_time=now,
            end_time=now + timedelta(minutes=30),
        )
        created = await svc.create_event(data, ORGANIZER, TENANT_ID)

        update = CalendarEventUpdate(title="Updated")
        updated = await svc.update_event(created.id, TENANT_ID, update)
        assert updated is not None
        assert updated.title == "Updated"

    @pytest.mark.asyncio
    async def test_cancel_event(self, db_session):
        svc = SchedulingService(db_session)
        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        data = CalendarEventCreate(
            title="Cancel me",
            start_time=now,
            end_time=now + timedelta(minutes=30),
        )
        created = await svc.create_event(data, ORGANIZER, TENANT_ID)

        success = await svc.cancel_event(created.id, TENANT_ID)
        assert success is True

        # Should be gone now (soft deleted)
        fetched = await svc.get_event(created.id, TENANT_ID)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_event(self, db_session):
        svc = SchedulingService(db_session)
        result = await svc.cancel_event("nonexistent-id", TENANT_ID)
        assert result is False


class TestSelectBestOption:
    """Tests for _select_best_option static method."""

    def test_selects_highest_score(self):
        from src.core.scheduling.schemas import SchedulingOption
        from src.core.scheduling.services.scheduling_service import SchedulingService

        now = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=now,
                end_time=now + timedelta(hours=1),
                confidence_score=0.3,
            ),
            SchedulingOption(
                start_time=now + timedelta(hours=2),
                end_time=now + timedelta(hours=3),
                confidence_score=0.9,
            ),
            SchedulingOption(
                start_time=now + timedelta(hours=4),
                end_time=now + timedelta(hours=5),
                confidence_score=0.6,
            ),
        ]
        best = SchedulingService._select_best_option(options)
        assert best.confidence_score == 0.9

    def test_empty_options_raises(self):
        from src.core.scheduling.services.scheduling_service import (
            SchedulingError,
            SchedulingService,
        )

        with pytest.raises(SchedulingError, match="empty options list"):
            SchedulingService._select_best_option([])
