"""PostgreSQL integration tests for the AUDIT-004 memory purge (GDPR art. 17).

Verifies on a real database what the SQLite unit tests cannot:
- the purge physically removes the row AND its pgvector embedding column
  (a real Vector type, not the SQLite JSON stand-in);
- the per-tenant orchestration works on the real stack (TenantFilterBypass
  for discovery + explicit per-tenant WHERE -- never a cross-tenant DELETE).

Skips module-level when no PostgreSQL test database is available (runs in CI).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant
from src.domains.memory.models import EMBEDDING_DIMS, MemoryItem
from src.domains.memory.services.memory_purge_service import (
    MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS,
    purge_expired_soft_deletes,
    purge_soft_deleted_items,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.multi_tenant,
]


def _expired() -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        days=MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS + 1
    )


async def _seed_tenant(session: AsyncSession, slug: str) -> int:
    tenant = Tenant(name=f"Purge Tenant {slug}", slug=f"purge-tenant-{slug}")
    session.add(tenant)
    await session.flush()
    await session.commit()
    return int(tenant.id)


def _make_item(
    tenant_id: int,
    *,
    deleted_at: datetime | None,
    with_embedding: bool = True,
) -> MemoryItem:
    return MemoryItem(
        tenant_id=tenant_id,
        memory_type="semantic",
        content="purge integration item",
        source_type="chat",
        privacy_scope="tenant",
        status="accepted",
        tags=[],
        entities=[],
        provenance=[],
        deleted_at=deleted_at,
        content_embedding=[0.05] * EMBEDDING_DIMS if with_embedding else None,
    )


async def _physical_count(session: AsyncSession, tenant_id: int) -> int:
    """Row count via raw SQL -- no ORM filter, no deleted_at condition."""
    result = await session.execute(
        text("SELECT count(*) FROM memory_items WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    return int(result.scalar_one())


async def test_purge_removes_row_and_embedding_physically(
    postgres_session: AsyncSession,
) -> None:
    """Expired soft-deleted row (with a real pgvector embedding) is physically gone."""
    tid = await _seed_tenant(postgres_session, "phys")
    postgres_session.add(_make_item(tid, deleted_at=_expired(), with_embedding=True))
    await postgres_session.commit()
    assert await _physical_count(postgres_session, tid) == 1

    deleted = await purge_soft_deleted_items(postgres_session, tid)
    await postgres_session.commit()

    assert deleted == 1
    assert await _physical_count(postgres_session, tid) == 0, (
        "The row -- and with it the content_embedding column -- must be physically "
        "erased; soft-delete alone never satisfies GDPR art. 17."
    )


async def test_purge_is_tenant_scoped_on_real_db(
    postgres_session: AsyncSession,
) -> None:
    """Purging tenant A must leave tenant B rows physically untouched."""
    tid_a = await _seed_tenant(postgres_session, "a")
    tid_b = await _seed_tenant(postgres_session, "b")
    postgres_session.add(_make_item(tid_a, deleted_at=_expired()))
    postgres_session.add(_make_item(tid_b, deleted_at=_expired()))
    await postgres_session.commit()

    deleted = await purge_soft_deleted_items(postgres_session, tid_a)
    await postgres_session.commit()

    assert deleted == 1
    assert await _physical_count(postgres_session, tid_a) == 0
    assert await _physical_count(postgres_session, tid_b) == 1, (
        "Cross-tenant delete is a P0; tenant B's row must survive."
    )


async def test_orchestration_purges_per_tenant_on_real_db(
    postgres_session: AsyncSession,
) -> None:
    """Full orchestration: discovery under TenantFilterBypass, per-tenant DELETEs,
    active rows and in-grace rows survive."""
    tid_a = await _seed_tenant(postgres_session, "orch-a")
    tid_b = await _seed_tenant(postgres_session, "orch-b")
    postgres_session.add(_make_item(tid_a, deleted_at=_expired()))
    postgres_session.add(_make_item(tid_b, deleted_at=_expired()))
    postgres_session.add(_make_item(tid_b, deleted_at=None))  # active: survives
    postgres_session.add(
        _make_item(tid_b, deleted_at=datetime.now(timezone.utc), with_embedding=False)
    )  # within grace: survives
    await postgres_session.commit()

    @asynccontextmanager
    async def _fake_session() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    from unittest.mock import patch

    with patch(
        "src.domains.memory.services.memory_purge_service.get_db_session",
        _fake_session,
    ):
        result: dict[str, Any] = await purge_expired_soft_deletes()

    assert result["per_tenant"][tid_a] == 1
    assert result["per_tenant"][tid_b] == 1
    assert await _physical_count(postgres_session, tid_a) == 0
    assert await _physical_count(postgres_session, tid_b) == 2

    # Idempotent on the real database too.
    with patch(
        "src.domains.memory.services.memory_purge_service.get_db_session",
        _fake_session,
    ):
        second: dict[str, Any] = await purge_expired_soft_deletes()

    assert second["per_tenant"].get(tid_a, 0) == 0
    assert second["per_tenant"].get(tid_b, 0) == 0
