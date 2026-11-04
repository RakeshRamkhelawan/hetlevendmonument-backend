"""Security tests: scheduling tenant isolation.

Verifies that no scheduling data leaks across tenant boundaries.
All repositories must enforce tenant_id on every query.

Uses in-memory SQLite — no Postgres required.
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
from src.core.scheduling.services.conflict_service import ConflictDetectionService

TENANT_A = 101
TENANT_B = 202
USER = "shared-user"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:sec_sched?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


def _at(hour: int) -> datetime:
    return datetime(2025, 8, 1, hour, 0, tzinfo=timezone.utc)


# -------------------------------------------------------------------------
# CalendarEvent isolation
# -------------------------------------------------------------------------


class TestCalendarEventTenantIsolation:
    @pytest.mark.asyncio
    async def test_event_invisible_to_other_tenant(self, db):
        """Event created for tenant A must not be retrievable by tenant B."""
        repo = CalendarEventRepository(db)
        ev = CalendarEvent(
            tenant_id=TENANT_A,
            title="Secret meeting",
            start_time=_at(10),
            end_time=_at(11),
            organizer_id=USER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        created = await repo.create(ev)

        result = await repo.get_by_id(created.id, TENANT_B)
        assert result is None, "Tenant B must not see Tenant A's events"

    @pytest.mark.asyncio
    async def test_list_events_scoped_to_tenant(self, db):
        """list_by_user_in_range must only return the requesting tenant's events."""
        repo = CalendarEventRepository(db)
        for tenant in (TENANT_A, TENANT_B):
            ev = CalendarEvent(
                tenant_id=tenant,
                title="Meeting",
                start_time=_at(10),
                end_time=_at(11),
                organizer_id=USER,
                event_type="meeting",
                status="confirmed",
                priority=3,
            )
            await repo.create(ev)

        events = await repo.list_by_user_in_range(
            TENANT_A,
            USER,
            start=datetime(2025, 8, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 8, 2, 0, 0, tzinfo=timezone.utc),
        )
        assert all(e.tenant_id == TENANT_A for e in events)

    @pytest.mark.asyncio
    async def test_overlap_query_scoped_to_tenant(self, db):
        """Conflict detection must not cross tenant boundaries."""
        repo = CalendarEventRepository(db)
        # Create overlapping event in TENANT_B
        ev_b = CalendarEvent(
            tenant_id=TENANT_B,
            title="B's busy slot",
            start_time=_at(10),
            end_time=_at(11),
            organizer_id=USER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        await repo.create(ev_b)

        # TENANT_A asking about same user+time should see NO conflict
        overlaps = await repo.find_overlapping(
            tenant_id=TENANT_A,
            user_id=USER,
            start=_at(10),
            end=_at(11),
        )
        assert len(overlaps) == 0, "Tenant A must not see Tenant B's events as conflicts"

    @pytest.mark.asyncio
    async def test_soft_delete_cannot_delete_other_tenants_event(self, db):
        """soft_delete with wrong tenant_id must fail silently."""
        repo = CalendarEventRepository(db)
        ev = CalendarEvent(
            tenant_id=TENANT_A,
            title="Protected",
            start_time=_at(10),
            end_time=_at(11),
            organizer_id=USER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        created = await repo.create(ev)

        success = await repo.soft_delete(created.id, TENANT_B)
        assert success is False

        # Event must still exist for correct tenant
        still_exists = await repo.get_by_id(created.id, TENANT_A)
        assert still_exists is not None


# -------------------------------------------------------------------------
# TimeBlock isolation
# -------------------------------------------------------------------------


class TestTimeBlockTenantIsolation:
    @pytest.mark.asyncio
    async def test_hard_blocks_scoped_to_tenant(self, db):
        repo = TimeBlockRepository(db)
        for tenant in (TENANT_A, TENANT_B):
            block = TimeBlock(
                tenant_id=tenant,
                user_id=USER,
                block_type="focus_time",
                start_time=_at(9),
                end_time=_at(11),
                is_hard_block=True,
            )
            await repo.create(block)

        blocks = await repo.find_hard_blocks_in_range(
            tenant_id=TENANT_A,
            user_id=USER,
            start=datetime(2025, 8, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 8, 2, 0, 0, tzinfo=timezone.utc),
        )
        assert all(b.tenant_id == TENANT_A for b in blocks)


# -------------------------------------------------------------------------
# ConflictDetectionService isolation
# -------------------------------------------------------------------------


class TestConflictServiceTenantIsolation:
    @pytest.mark.asyncio
    async def test_conflict_service_does_not_cross_tenants(self, db):
        """ConflictDetectionService must respect tenant_id in all queries."""
        event_repo = CalendarEventRepository(db)
        block_repo = TimeBlockRepository(db)

        # Add a confirmed event for TENANT_B
        ev = CalendarEvent(
            tenant_id=TENANT_B,
            title="B meeting",
            start_time=_at(10),
            end_time=_at(11),
            organizer_id=USER,
            event_type="meeting",
            status="confirmed",
            priority=3,
        )
        await event_repo.create(ev)

        svc = ConflictDetectionService(event_repo, block_repo)
        conflicts = await svc.check_conflicts(
            tenant_id=TENANT_A,
            organizer_id=USER,
            participant_ids=[],
            start=_at(10),
            end=_at(11),
        )
        assert (
            len(conflicts) == 0
        ), "ConflictDetectionService must not expose Tenant B's data to Tenant A"


# -------------------------------------------------------------------------
# Preference isolation
# -------------------------------------------------------------------------


class TestPreferenceTenantIsolation:
    @pytest.mark.asyncio
    async def test_preferences_scoped_to_tenant(self, db):
        repo = PreferenceRepository(db)
        pref = SchedulingPreference(
            tenant_id=TENANT_A,
            user_id=USER,
            timezone_name="Europe/Amsterdam",
            working_hours_start="09:00",
            working_hours_end="17:00",
            preferred_duration_minutes=30,
            buffer_minutes=5,
        )
        await repo.upsert(pref)

        result = await repo.get_by_user(TENANT_B, USER)
        assert result is None, "Tenant B must not see Tenant A's preferences"


# -------------------------------------------------------------------------
# Constraint isolation
# -------------------------------------------------------------------------


class TestConstraintTenantIsolation:
    @pytest.mark.asyncio
    async def test_constraints_scoped_to_tenant(self, db):
        repo = ConstraintRepository(db)
        c = SchedulingConstraint(
            tenant_id=TENANT_A,
            user_id=USER,
            constraint_type="no_early_meetings",
            is_hard=True,
        )
        repo.db.add(c)
        await repo.db.flush()

        result = await repo.list_by_user(TENANT_B, USER)
        assert len(result) == 0, "Tenant B must not see Tenant A's constraints"
