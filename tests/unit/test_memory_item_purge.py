"""AUDIT-004 regression tests: echte purge voor Twin-geheugen (GDPR art. 17).

Bevinding (CRITICAL/P0): MemoryWriteService.soft_delete_item zet alleen
deleted_at -- geen enkele taak of endpoint verwijdert de rij of de
bijbehorende embedding daadwerkelijk. Een expliciet AVG-verwijderverzoek
(art. 17) kon daardoor niet worden uitgevoerd.

Deze tests pinnen de fix:

- purge_soft_deleted_items: fysieke DELETE van soft-deleted memory_items na de
  grace period, tenant-scoped. De embedding (content_embedding) is een kolom op
  dezelfde rij (models.py) en verdwijnt dus mee -- bewezen door te seeden met
  een gevulde embedding en te eisen dat de rij fysiek weg is.
- purge_expired_soft_deletes: per-tenant orchestratie onder TenantFilterBypass,
  nooit een cross-tenant DELETE.
- DSARService._purge_memory_items: het canonieke art.-17-pad (delete_user_data)
  purgt memory-items van het subject fysiek, in hard- EN soft-mode -- consistent
  met CVA conversations en agentic_tasks (embeddings zijn niet anonimiseerbaar).
- De Dramatiq actor purge_soft_deleted_memory_items voert de orchestratie uit.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# pgvector's Vector type has no SQLite compiler; render it as JSON so the
# MemoryItem table can be created on the in-memory SQLite test database.
# Affects only SQLite compilation inside this test process.
try:
    from pgvector.sqlalchemy import Vector as _PGVector
    from sqlalchemy.ext.compiler import compiles

    @compiles(_PGVector, "sqlite")
    def _compile_vector_as_json(element: Any, compiler: Any, **kw: Any) -> str:
        return "JSON"

except ImportError:  # pragma: no cover - pgvector absent: model already falls back to JSON
    pass

from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.dsar_service import DSARService
from src.domains.memory.models import EMBEDDING_DIMS, MemoryItem
from src.domains.memory.services.memory_purge_service import (
    MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS,
    purge_expired_soft_deletes,
    purge_soft_deleted_items,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    tenant_id: int,
    *,
    user_id: int | None = None,
    deleted_at: datetime | None = None,
    with_embedding: bool = False,
) -> MemoryItem:
    """Build a MemoryItem with all required non-null fields populated."""
    return MemoryItem(
        tenant_id=tenant_id,
        user_id=user_id,
        memory_type="semantic",
        content="purge-test item",
        source_type="chat",
        privacy_scope="tenant",
        status="accepted",
        tags=[],
        entities=[],
        provenance=[],
        deleted_at=deleted_at,
        content_embedding=[0.1] * EMBEDDING_DIMS if with_embedding else None,
    )


def _expired(grace_period_days: int = MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS) -> datetime:
    """A deleted_at timestamp older than the grace period."""
    return datetime.now(timezone.utc) - timedelta(days=grace_period_days + 1)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Real in-memory SQLite session with only the memory_items table.

    SQLite does not enforce FK constraints by default, so the tenants/users
    FK targets need not exist. A real database (not a mock) is deliberate:
    the whole point of AUDIT-004 is that rows physically disappear.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(MemoryItem.__table__.create, checkfirst=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _count_all(db: AsyncSession, tenant_id: int) -> int:
    """Physical row count WITHOUT the deleted_at filter -- proves real erasure.

    `TenantFilterBypass` is hier verplicht, niet optioneel. `init_tenant_auto_filtering()`
    registreert een GLOBALE `do_orm_execute`-listener op `Session` (propagate=True) die
    nooit wordt opgeruimd. Zodra een eerdere test in dezelfde xdist-worker die registreert
    -- `tests/unit/test_tenant_query_filter.py` doet dat -- krijgt ook de eigen
    in-memory-sessie van dit bestand een automatisch tenantfilter, en dat filter is
    fail-secure: zonder tenant in de ContextVar levert het NUL rijen.

    Deze tests slaagden dus alleen zolang de sharding ze bij die andere test weghield. Op
    2026-08-01 gebeurde dat niet meer en vielen ze om -- reproduceerbaar met:

        pytest tests/unit/test_tenant_query_filter.py tests/unit/test_memory_item_purge.py

    De bypass is de gedocumenteerde weg voor precies dit geval (`TenantFilterBypass`
    noemt "Test fixtures" expliciet). Hij geldt alleen deze verificatiequery: de
    purge-code die getest WORDT blijft onverkort tenant-gescoped -- dat is wat
    `test_purge_is_tenant_scoped` aantoont.
    """
    with TenantFilterBypass():
        result = await db.execute(select(MemoryItem).where(MemoryItem.tenant_id == tenant_id))
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Pad A -- purge_soft_deleted_items (tenant-scoped physical DELETE)
# ---------------------------------------------------------------------------


class TestPurgeSoftDeletedItems:
    """Tests 1.1, 1.2, 1.3, 1.4 and 1.6 from the day-3 brief."""

    async def test_purge_removes_expired_soft_deleted_item_physically(
        self, db_session: AsyncSession
    ) -> None:
        """Test 1.1: soft-deleted row + embedding physically gone after purge."""
        db_session.add(_make_item(1, deleted_at=_expired(), with_embedding=True))
        await db_session.commit()
        assert await _count_all(db_session, 1) == 1

        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            deleted = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()

        assert deleted == 1
        assert await _count_all(db_session, 1) == 0, (
            "Row (and with it the content_embedding column) must be physically gone; "
            "soft-delete alone never satisfies GDPR art. 17."
        )

    async def test_purge_keeps_active_items(self, db_session: AsyncSession) -> None:
        """Test 1.2: items without deleted_at are never touched."""
        db_session.add(_make_item(1, deleted_at=None))
        await db_session.commit()

        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            deleted = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()

        assert deleted == 0
        assert await _count_all(db_session, 1) == 1

    async def test_purge_keeps_items_within_grace_period(self, db_session: AsyncSession) -> None:
        """Test 1.3: recently soft-deleted items stay within the grace period."""
        db_session.add(_make_item(1, deleted_at=datetime.now(timezone.utc)))
        await db_session.commit()

        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            deleted = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()

        assert deleted == 0
        assert await _count_all(db_session, 1) == 1

    async def test_purge_is_tenant_scoped(self, db_session: AsyncSession) -> None:
        """Test 1.4: purging tenant A must leave tenant B rows untouched."""
        db_session.add(_make_item(1, deleted_at=_expired()))
        db_session.add(_make_item(2, deleted_at=_expired()))
        await db_session.commit()

        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            deleted = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()

        assert deleted == 1
        assert await _count_all(db_session, 1) == 0
        assert (
            await _count_all(db_session, 2) == 1
        ), "Cross-tenant delete is a P0; tenant B's soft-deleted row must survive."

    async def test_purge_is_idempotent(self, db_session: AsyncSession) -> None:
        """Test 1.6: a second purge run deletes nothing and does not fail."""
        db_session.add(_make_item(1, deleted_at=_expired()))
        await db_session.commit()

        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            first = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()
        # TenantFilterBypass net als de echte aanroeper
        # (memory_purge_service.py:106): een worker heeft geen tenant-ContextVar.
        with TenantFilterBypass():
            second = await purge_soft_deleted_items(db_session, tenant_id=1)
        await db_session.commit()

        assert first == 1
        assert second == 0


# ---------------------------------------------------------------------------
# Pad A -- purge_expired_soft_deletes (per-tenant orchestratie)
# ---------------------------------------------------------------------------


class TestPurgeExpiredSoftDeletesOrchestration:
    """The actor-facing orchestration: discovery + per-tenant loop."""

    async def test_orchestration_purges_per_tenant_and_reports(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_item(1, deleted_at=_expired()))
        db_session.add(_make_item(2, deleted_at=_expired()))
        db_session.add(_make_item(2, deleted_at=None))  # active: must survive
        db_session.add(_make_item(3, deleted_at=None))  # tenant without purgeables
        await db_session.commit()

        @asynccontextmanager
        async def _fake_session() -> AsyncGenerator[AsyncSession, None]:
            yield db_session

        with patch(
            "src.domains.memory.services.memory_purge_service.get_db_session",
            _fake_session,
        ):
            result = await purge_expired_soft_deletes()

        assert result["items_purged"] == 2
        assert result["per_tenant"] == {1: 1, 2: 1}
        assert await _count_all(db_session, 1) == 0
        assert await _count_all(db_session, 2) == 1
        assert await _count_all(db_session, 3) == 1

    async def test_orchestration_is_idempotent_on_empty_set(self, db_session: AsyncSession) -> None:
        @asynccontextmanager
        async def _fake_session() -> AsyncGenerator[AsyncSession, None]:
            yield db_session

        with patch(
            "src.domains.memory.services.memory_purge_service.get_db_session",
            _fake_session,
        ):
            result = await purge_expired_soft_deletes()

        assert result["items_purged"] == 0
        assert result["per_tenant"] == {}


# ---------------------------------------------------------------------------
# Pad A -- Dramatiq actor
# ---------------------------------------------------------------------------


class TestPurgeActor:
    """The scheduled actor must execute the orchestration."""

    def test_actor_runs_purge_orchestration(self) -> None:
        """Sync test: the actor body calls asyncio.run(purge_expired_soft_deletes()).

        Must NOT be an async test -- asyncio.run() cannot run inside the
        pytest-asyncio event loop (CLAUDE.md valkuil: fresh loop per call).
        """
        from src.domains.memory import tasks as memory_tasks

        with patch(
            "src.domains.memory.tasks.purge_expired_soft_deletes",
            new=AsyncMock(return_value={"items_purged": 0, "per_tenant": {}}),
        ) as purge_mock:
            memory_tasks.purge_soft_deleted_memory_items()

        purge_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Pad B -- DSARService._purge_memory_items (canonieke art.-17 route)
# ---------------------------------------------------------------------------


def _dsar_svc() -> DSARService:
    """DSARService with a mocked db (pattern: tests/unit/governance/test_dsar_dag7.py)."""
    db = AsyncMock()

    @asynccontextmanager
    async def _nested() -> AsyncGenerator[None, None]:
        yield

    db.begin_nested = lambda: _nested()
    return DSARService(db=db)


def _user_result(user: MagicMock) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    res.scalars.return_value.all.return_value = []
    res.mappings.return_value.all.return_value = []
    return res


class TestDSARMemoryItemPurge:
    """Helper behaviour (test 1.5 from the day-3 brief)."""

    async def test_purge_memory_items_returns_rowcount(self) -> None:
        svc = _dsar_svc()
        result = MagicMock()
        result.rowcount = 4
        svc._db.execute = AsyncMock(return_value=result)

        deleted = await svc._purge_memory_items(tenant_id=7, user_id="5")

        assert deleted == 4

    @pytest.mark.security
    async def test_purge_memory_items_is_tenant_and_user_scoped(self) -> None:
        svc = _dsar_svc()
        result = MagicMock()
        result.rowcount = 0
        captured: dict[str, Any] = {}

        async def _execute(stmt: Any, *a: Any, **k: Any) -> MagicMock:
            captured["stmt"] = stmt
            return result

        svc._db.execute = _execute

        await svc._purge_memory_items(tenant_id=7, user_id="5")

        stmt = captured["stmt"]
        sql = str(stmt)
        assert "memory_items" in sql
        assert "tenant_id" in sql and "user_id" in sql
        bound = set(stmt.compile().params.values())
        assert 7 in bound  # tenant_id
        assert 5 in bound  # user_id (coerced to int)

    async def test_purge_memory_items_returns_zero_on_error(self) -> None:
        """A failing memory purge must not break the surrounding DSAR delete."""
        svc = _dsar_svc()
        svc._db.execute = AsyncMock(side_effect=RuntimeError("db down"))

        deleted = await svc._purge_memory_items(tenant_id=7, user_id="5")

        assert deleted == 0


class TestDSARMemoryItemPurgeWiring:
    """delete_user_data must invoke the memory purge in BOTH modes."""

    def _wired_svc(self) -> DSARService:
        svc = _dsar_svc()
        user = MagicMock()
        user.id = 123
        user.tenant_id = 1
        user.is_active = True
        svc._db.execute = AsyncMock(return_value=_user_result(user))
        svc._create_audit_log = AsyncMock()
        svc._delete_agentic_tasks = AsyncMock(return_value=0)
        svc._clear_copilot_sessions = AsyncMock(return_value=0)
        svc._purge_memory_items = AsyncMock(return_value=3)
        return svc

    @pytest.mark.security
    async def test_hard_delete_wires_memory_item_purge(self) -> None:
        svc = self._wired_svc()

        await svc.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=True,
            requested_by_user_id="admin",
            is_admin=True,
        )

        svc._purge_memory_items.assert_awaited_once_with(1, "123")

    @pytest.mark.security
    async def test_soft_delete_wires_memory_item_purge(self) -> None:
        """Soft mode also purges physically -- embeddings cannot be anonymised,
        consistent with CVA conversations and agentic_tasks (GDPR-A17-004)."""
        svc = self._wired_svc()

        await svc.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=False,
            requested_by_user_id="123",
            is_admin=False,
        )

        svc._purge_memory_items.assert_awaited_once_with(1, "123")
