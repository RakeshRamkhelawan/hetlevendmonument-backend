"""Pytest configuration and fixtures for ALS tests.

Uses real Docker services:
- PostgreSQL on port 5435
- Redis on port 6385
"""

import asyncio
import os
import uuid
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Set test environment before any imports
os.environ["ENVIRONMENT"] = "test"
# Server uit de centrale opgave; de databasenaam blijft `sanskritisetu_test` omdat die
# iets anders is dan `sanskritisetu` (ADR-036 OP-243). Stond hardgecodeerd op 5435 --
# precies de poort waar op 2026-09-14 een vergeten act-container op luisterde.
from tests.fixtures.testdatabase import testdatabase_url  # noqa: E402

os.environ["DATABASE_URL"] = testdatabase_url(database="sanskritisetu_test")
os.environ["REDIS_URL"] = "redis://localhost:6385/0"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-long-for-als-tests"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-32-chars-for-als-tests"
os.environ["SIGNAL_COOLDOWN_SECONDS"] = "1"

from src.core.als.infrastructure.redis_pool import RedisPoolManager
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.als.models.collective_knowledge import CollectiveKnowledge
from src.core.als.models.immune_antibody import ImmuneAntibody
from src.core.als.models.immune_memory_cell import ImmuneMemoryCell
from src.core.als.models.organism_registry import OrganismRegistry
from src.core.als.models.signal_audit_log import SignalAuditLog
from src.core.database.database import Base

POSTGRES_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]


async def _skip_unless_postgres_available() -> None:
    probe_engine = create_async_engine(
        POSTGRES_URL,
        poolclass=NullPool,
        echo=False,
    )
    try:
        async with probe_engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        pytest.skip(f"ALS PostgreSQL test database unavailable: {exc}")
    finally:
        await probe_engine.dispose()


async def _skip_unless_redis_available() -> None:
    client = redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
    )
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"ALS Redis service unavailable: {exc}")
    finally:
        await client.aclose()


# =============================================================================
# Event Loop
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Don't close the loop here - let pytest handle it at process exit


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine connected to Docker PostgreSQL."""
    await _skip_unless_postgres_available()

    engine = create_async_engine(
        POSTGRES_URL,
        poolclass=NullPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup - drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create fresh database session for each test."""
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        await session.rollback()


# =============================================================================
# Redis Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def redis_pool():
    """Create Redis pool connected to Docker Redis."""
    await _skip_unless_redis_available()

    pool = RedisPoolManager()
    yield pool
    # Note: Don't close the pool here - it causes event loop issues
    # The pool will be cleaned up when the process exits


@pytest.fixture
async def signal_bus(redis_pool):
    """Create SignalBus instance."""
    bus = SignalBus(redis_pool)
    yield bus


# =============================================================================
# Tenant Fixtures
# =============================================================================


@pytest.fixture
async def tenant_a(db_session: AsyncSession) -> OrganismRegistry:
    """Create test tenant A."""
    # Use a unique tenant ID for isolation
    tenant_id = 10001

    # Store in registry for reference
    registry = OrganismRegistry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        agent_id="tenant_a_marker",
        agent_type="marker",
        department="test",
        status="healthy",
    )
    db_session.add(registry)
    await db_session.commit()

    return registry


@pytest.fixture
async def tenant_b(db_session: AsyncSession) -> OrganismRegistry:
    """Create test tenant B (for cross-tenant tests)."""
    tenant_id = 10002

    registry = OrganismRegistry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        agent_id="tenant_b_marker",
        agent_type="marker",
        department="test",
        status="healthy",
    )
    db_session.add(registry)
    await db_session.commit()

    return registry


# =============================================================================
# Signal Fixtures
# =============================================================================


@pytest.fixture
def valid_signal() -> Signal:
    """Create a valid signal for happy path tests."""
    return Signal(
        tenant_id=10001,
        source_agent_id="test_agent",
        target_agent_ids=["target_agent"],
        tier=SignalTier.COGNITIVE,
        payload={"action": "test", "data": "value"},
    )


@pytest.fixture
def broadcast_signal() -> Signal:
    """Create a broadcast signal."""
    return Signal(
        tenant_id=10001,
        source_agent_id="test_agent",
        target_agent_ids=[],  # Empty = broadcast
        tier=SignalTier.BROADCAST,
        payload={"message": "hello all"},
    )


@pytest.fixture
def reflex_signal() -> Signal:
    """Create a high-priority REFLEX signal."""
    return Signal(
        tenant_id=10001,
        source_agent_id="test_agent",
        target_agent_ids=["target_agent"],
        tier=SignalTier.REFLEX,
        payload={"urgent": True, "action": "alert"},
    )


@pytest.fixture
def invalid_signal_missing_tenant() -> dict:
    """Invalid signal data for unhappy path tests."""
    return {
        "source_agent_id": "test_agent",
        "target_agent_ids": [],
        "tier": SignalTier.COGNITIVE,
        "payload": {"test": True},
        # Missing tenant_id!
    }


# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for isolated tests."""
    from unittest.mock import AsyncMock, MagicMock

    client = AsyncMock()
    client.publish = AsyncMock(return_value=1)
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.exists = AsyncMock(return_value=0)
    client.delete = AsyncMock(return_value=1)
    client.ping = AsyncMock()
    return client


@pytest.fixture
def tenant_factory(db_session):
    """Factory for creating tenants with unique IDs."""
    _counter = 20000

    async def _create():
        nonlocal _counter
        _counter += 1

        registry = OrganismRegistry(
            id=uuid.uuid4(),
            tenant_id=_counter,
            agent_id=f"test_tenant_{_counter}",
            agent_type="test",
            department="test",
            status="healthy",
        )
        db_session.add(registry)
        await db_session.commit()
        return registry

    return _create
