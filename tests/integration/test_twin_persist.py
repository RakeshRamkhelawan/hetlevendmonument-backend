"""Integration test: Digital Twin observations persist to PostgreSQL.

Verifies that the batch manager + default persist function actually writes
rows into user_behavior_observations on the test database (port 5455).
"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import os
from tests.fixtures.testdatabase import testdatabase_url

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    testdatabase_url(),
)


@pytest.fixture
async def db_session():
    """Fresh async session against the test database."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_insert_observation_batch_creates_rows(db_session: AsyncSession) -> None:
    """Batch-insert 5 observations and verify they land in the DB."""
    from src.core.learning.batching.batch_manager import PendingObservation
    from src.core.learning.repositories.observation_repository import insert_observation_batch

    tenant_id = 1
    observations = [
        PendingObservation(
            tenant_id=tenant_id,
            human_user_id="user_001",
            session_id="sess_abc",
            behavior_type="file_edit",
            context={"file": "main.py"},
            outcome_metrics={"lines_changed": 12},
            confidence_score=0.95,
            timestamp=time.time(),
        )
        for _ in range(5)
    ]

    await insert_observation_batch(db_session, observations)
    await db_session.commit()

    result = await db_session.execute(
        select(func.count()).select_from(text("user_behavior_observations"))
    )
    count = result.scalar()
    assert count is not None
    assert count >= 5

    # Verify tenant isolation
    result2 = await db_session.execute(
        select(text("behavior_type"))
        .select_from(text("user_behavior_observations"))
        .where(text("human_user_id = 'user_001'"))
    )
    rows = result2.scalars().all()
    assert all(bt == "file_edit" for bt in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_manager_default_persist_fn_flushes_to_db() -> None:
    """Singleton batch manager with explicit persist_fn writes to PostgreSQL."""
    from src.core.learning.batching.batch_manager import (
        ObservationBatchManager,
        PendingObservation,
        get_batch_manager,
        reset_batch_manager,
        shutdown_batch_manager,
    )
    from src.core.learning.repositories.observation_repository import (
        insert_observation_batch,
    )

    # Ensure a clean singleton for this test
    await shutdown_batch_manager()
    reset_batch_manager()

    engine = create_async_engine(_TEST_DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _test_persist_fn(batch: list[PendingObservation]) -> None:
        async with session_factory() as db:
            await insert_observation_batch(db, batch)
            await db.commit()

    tenant_id = 1
    mgr = await get_batch_manager(persist_fn=_test_persist_fn)

    obs = PendingObservation(
        tenant_id=tenant_id,
        human_user_id="batch_user_001",
        session_id="sess_batch",
        behavior_type="rapid_switch",
        context={"switches": 3},
        outcome_metrics={"time_spent": 45},
        confidence_score=0.8,
        timestamp=time.time(),
    )

    await mgr.add(obs)

    # Force flush
    await mgr.flush()

    # Verify in DB
    async with session_factory() as db:
        result = await db.execute(
            select(text("human_user_id, behavior_type"))
            .select_from(text("user_behavior_observations"))
            .where(text("human_user_id = 'batch_user_001'"))
        )
        rows = result.all()
        assert len(rows) >= 1
        assert rows[0][1] == "rapid_switch"

    await engine.dispose()

    # Cleanup
    await shutdown_batch_manager()
    reset_batch_manager()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_twin_tables_exist() -> None:
    """All four Digital Twin tables must exist after Alembic migration."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename IN (
                    'user_behavior_observations',
                    'user_cognitive_profiles',
                    'user_twin_consent',
                    'focus_builder_accepted_workflows'
                )
                """
            )
        )
        tables = {row[0] for row in result}

    await engine.dispose()

    expected = {
        "user_behavior_observations",
        "user_cognitive_profiles",
        "user_twin_consent",
        "focus_builder_accepted_workflows",
    }
    assert tables == expected, f"Missing twin tables: {expected - tables}"
