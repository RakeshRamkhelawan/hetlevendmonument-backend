"""Unit tests for scheduling repository layer.

Tests tenant isolation, CRUD operations, and overlap queries.
Uses in-memory SQLite so no Postgres is required.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database.database import Base
from src.core.models.rbac_models import Tenant  # noqa: F401 - registers FK target
from src.core.scheduling.models import (
    CalendarEvent,
    SchedulingConstraint,
    SchedulingPreference,
    TimeBlock,
)
from src.core.scheduling.repository import (
    CalendarEventRepository,
    ConstraintRepository,
    PreferenceRepository,
    TimeBlockRepository,
)

TENANT_A = 10
TENANT_B = 20
USER_1 = "user-1"
USER_2 = "user-2"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:repo_test?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


def _event(
    tenant_id: int, organizer: str, start_hour: int, duration_h: int = 1, **kw
) -> CalendarEvent:
    start = datetime(2025, 7, 1, start_hour, 0, tzinfo=timezone.utc)
    return CalendarEvent(
        tenant_id=tenant_id,
        title=kw.pop("title", "Meeting"),
        start_time=start,
        end_time=start + timedelta(hours=duration_h),
        organizer_id=organizer,
        user_id=kw.pop("user_id", organizer),
        event_type="meeting",
        status="confirmed",
        priority=3,
        **kw,
    )


# -------------------------------------------------------------------------
# CalendarEventRepository
# -------------------------------------------------------------------------


class TestCalendarEventRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        repo = CalendarEventRepository(db)
        ev = await repo.create(_event(TENANT_A, USER_1, 10))
        assert ev.id is not None

        fetched = await repo.get_by_id(ev.id, TENANT_A)
        assert fetched is not None
        assert fetched.title == "Meeting"

    @pytest.mark.asyncio
    async def test_get_by_id_wrong_tenant_returns_none(self, db):
        repo = CalendarEventRepository(db)
        ev = await repo.create(_event(TENANT_A, USER_1, 10))

        result = await repo.get_by_id(ev.id, TENANT_B)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_user_in_range_scoped(self, db):
        repo = CalendarEventRepository(db)
        await repo.create(_event(TENANT_A, USER_1, 10))
        await repo.create(_event(TENANT_B, USER_1, 10))  # different tenant

        window_start = datetime(2025, 7, 1, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2025, 7, 2, 0, 0, tzinfo=timezone.utc)
        events = await repo.list_by_user_in_range(TENANT_A, USER_1, window_start, window_end)

        # De telling hoort erbij: `all(...)` op een LEGE lijst is waar, dus zonder deze
        # regel bleef de test groen als de repository niets meer teruggaf (gemeten in de
        # Gate 2-review, ADR-036 OP-196). Er is precies een event van tenant A in dit venster.
        assert len(events) == 1
        assert all(e.tenant_id == TENANT_A for e in events)

    @pytest.mark.asyncio
    async def test_find_overlapping_detects_overlap(self, db):
        repo = CalendarEventRepository(db)
        await repo.create(_event(TENANT_A, USER_1, 10))  # 10:00-11:00

        overlaps = await repo.find_overlapping(
            tenant_id=TENANT_A,
            user_id=USER_1,
            start=datetime(2025, 7, 1, 10, 30, tzinfo=timezone.utc),
            end=datetime(2025, 7, 1, 11, 30, tzinfo=timezone.utc),
        )
        assert len(overlaps) == 1

    @pytest.mark.asyncio
    async def test_find_overlapping_adjacent_no_conflict(self, db):
        repo = CalendarEventRepository(db)
        await repo.create(_event(TENANT_A, USER_1, 10))  # 10:00-11:00

        # Exactly adjacent: starts when existing ends
        overlaps = await repo.find_overlapping(
            tenant_id=TENANT_A,
            user_id=USER_1,
            start=datetime(2025, 7, 1, 11, 0, tzinfo=timezone.utc),
            end=datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc),
        )
        assert len(overlaps) == 0

    @pytest.mark.asyncio
    async def test_find_overlapping_exclude_event_id(self, db):
        repo = CalendarEventRepository(db)
        ev = await repo.create(_event(TENANT_A, USER_1, 10))

        overlaps = await repo.find_overlapping(
            tenant_id=TENANT_A,
            user_id=USER_1,
            start=datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2025, 7, 1, 11, 0, tzinfo=timezone.utc),
            exclude_event_id=ev.id,
        )
        assert len(overlaps) == 0

    @pytest.mark.asyncio
    async def test_soft_delete_hides_event(self, db):
        repo = CalendarEventRepository(db)
        ev = await repo.create(_event(TENANT_A, USER_1, 10))

        deleted = await repo.soft_delete(ev.id, TENANT_A)
        assert deleted is True

        fetched = await repo.get_by_id(ev.id, TENANT_A)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_soft_delete_wrong_tenant_returns_false(self, db):
        repo = CalendarEventRepository(db)
        ev = await repo.create(_event(TENANT_A, USER_1, 10))

        deleted = await repo.soft_delete(ev.id, TENANT_B)
        assert deleted is False


# -------------------------------------------------------------------------
# TimeBlockRepository
# -------------------------------------------------------------------------


class TestTimeBlockRepository:
    def _block(self, tenant_id: int, user_id: str, start_hour: int, hard: bool = True) -> TimeBlock:
        start = datetime(2025, 7, 1, start_hour, 0, tzinfo=timezone.utc)
        return TimeBlock(
            tenant_id=tenant_id,
            user_id=user_id,
            block_type="focus_time",
            start_time=start,
            end_time=start + timedelta(hours=2),
            is_hard_block=hard,
        )

    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        repo = TimeBlockRepository(db)
        block = await repo.create(self._block(TENANT_A, USER_1, 9))
        assert block.id is not None

        fetched = await repo.get_by_id(block.id, TENANT_A)
        assert fetched is not None

    @pytest.mark.asyncio
    async def test_find_hard_blocks_filters_soft(self, db):
        repo = TimeBlockRepository(db)
        await repo.create(self._block(TENANT_A, USER_1, 9, hard=True))
        await repo.create(self._block(TENANT_A, USER_1, 12, hard=False))

        hard_blocks = await repo.find_hard_blocks_in_range(
            tenant_id=TENANT_A,
            user_id=USER_1,
            start=datetime(2025, 7, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 7, 2, 0, 0, tzinfo=timezone.utc),
        )
        assert len(hard_blocks) == 1
        assert hard_blocks[0].is_hard_block is True

    @pytest.mark.asyncio
    async def test_tenant_isolation_time_blocks(self, db):
        repo = TimeBlockRepository(db)
        await repo.create(self._block(TENANT_A, USER_1, 9))
        await repo.create(self._block(TENANT_B, USER_1, 9))

        blocks = await repo.find_hard_blocks_in_range(
            tenant_id=TENANT_A,
            user_id=USER_1,
            start=datetime(2025, 7, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 7, 2, 0, 0, tzinfo=timezone.utc),
        )
        assert all(b.tenant_id == TENANT_A for b in blocks)

    @pytest.mark.asyncio
    async def test_soft_delete_time_block(self, db):
        repo = TimeBlockRepository(db)
        block = await repo.create(self._block(TENANT_A, USER_1, 9))

        success = await repo.soft_delete(block.id, TENANT_A)
        assert success is True

        fetched = await repo.get_by_id(block.id, TENANT_A)
        assert fetched is None


# -------------------------------------------------------------------------
# ConstraintRepository
# -------------------------------------------------------------------------


class TestConstraintRepository:
    @pytest.mark.asyncio
    async def test_create_and_list(self, db):
        repo = ConstraintRepository(db)
        c = SchedulingConstraint(
            tenant_id=TENANT_A,
            user_id=USER_1,
            constraint_type="no_early_meetings",
            is_hard=True,
        )
        repo.db.add(c)
        await repo.db.flush()

        constraints = await repo.list_by_user(TENANT_A, USER_1)
        assert len(constraints) >= 1
        assert constraints[0].constraint_type == "no_early_meetings"

    @pytest.mark.asyncio
    async def test_tenant_isolation_constraints(self, db):
        repo = ConstraintRepository(db)
        for tenant in (TENANT_A, TENANT_B):
            c = SchedulingConstraint(
                tenant_id=tenant,
                user_id=USER_1,
                constraint_type="buffer",
                is_hard=False,
            )
            repo.db.add(c)
        await repo.db.flush()

        result = await repo.list_by_user(TENANT_A, USER_1)
        assert all(c.tenant_id == TENANT_A for c in result)


# -------------------------------------------------------------------------
# PreferenceRepository
# -------------------------------------------------------------------------


class TestPreferenceRepository:
    @pytest.mark.asyncio
    async def test_upsert_creates(self, db):
        repo = PreferenceRepository(db)
        pref = SchedulingPreference(
            tenant_id=TENANT_A,
            user_id=USER_1,
            timezone_name="Europe/Amsterdam",
            working_hours_start="09:00",
            working_hours_end="17:00",
            preferred_duration_minutes=30,
            buffer_minutes=5,
        )
        result = await repo.upsert(pref)
        assert result.id is not None
        assert result.timezone_name == "Europe/Amsterdam"

    @pytest.mark.asyncio
    async def test_get_by_user_returns_none_if_missing(self, db):
        repo = PreferenceRepository(db)
        result = await repo.get_by_user(TENANT_A, "unknown-user")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_user_tenant_isolation(self, db):
        repo = PreferenceRepository(db)
        pref_a = SchedulingPreference(
            tenant_id=TENANT_A,
            user_id=USER_1,
            timezone_name="UTC",
            working_hours_start="09:00",
            working_hours_end="17:00",
            preferred_duration_minutes=30,
            buffer_minutes=5,
        )
        await repo.upsert(pref_a)

        result = await repo.get_by_user(TENANT_B, USER_1)
        assert result is None
