"""Unit tests for src.core.database.read_replica."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine as orig_create_async_engine,
)

from src.core.database.read_replica import (
    ReplicaStrategy,
    ReplicaConfig,
    ReadReplicaRouter,
    create_replica_router,
)


@pytest.fixture(autouse=True)
def patch_create_async_engine_for_sqlite():
    """SQLite memory pools do not accept pool_size or max_overflow."""
    def _safe_create_engine(url, *args, **kwargs):
        if "sqlite" in url:
            kwargs.pop("pool_size", None)
            kwargs.pop("max_overflow", None)
            kwargs.pop("pool_pre_ping", None)
        return orig_create_async_engine(url, *args, **kwargs)

    with patch("src.core.database.read_replica.create_async_engine", side_effect=_safe_create_engine):
        yield


def test_replica_strategy_enum():
    """Validates enum strategy options."""
    assert ReplicaStrategy.RANDOM == "random"
    assert ReplicaStrategy.ROUND_ROBIN == "round_robin"
    assert ReplicaStrategy.LEAST_CONNECTIONS == "least_connections"


def test_replica_config_defaults():
    """Validates ReplicaConfig defaults."""
    cfg = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    assert cfg.weight == 1
    assert cfg.region == "default"


@pytest.mark.asyncio
async def test_read_replica_router_write_session_always_uses_primary():
    """get_write_session initializes and returns session from primary."""
    router = ReadReplicaRouter(primary_url="sqlite+aiosqlite:///:memory:")
    session = router.get_write_session()
    assert isinstance(session, AsyncSession)
    await session.close()
    await router.close()


@pytest.mark.asyncio
async def test_read_replica_router_read_session_prefer_primary():
    """get_read_session with prefer_primary=True returns primary session."""
    replica1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[replica1],
    )
    router.initialize()

    session = router.get_read_session(prefer_primary=True)
    assert isinstance(session, AsyncSession)
    assert session.bind is router._primary_engine
    await session.close()
    await router.close()


@pytest.mark.asyncio
async def test_read_replica_router_round_robin_selection():
    """Selects replicas in round-robin sequence."""
    r1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    r2 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[r1, r2],
        strategy=ReplicaStrategy.ROUND_ROBIN,
    )
    router.initialize()

    engine1 = router._select_replica()
    engine2 = router._select_replica()
    engine3 = router._select_replica()

    assert engine1 is router._replica_engines[0]["engine"]
    assert engine2 is router._replica_engines[1]["engine"]
    assert engine3 is router._replica_engines[0]["engine"]

    await router.close()


@pytest.mark.asyncio
async def test_read_replica_router_random_selection():
    """Random selection picks from healthy replicas."""
    r1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[r1],
        strategy=ReplicaStrategy.RANDOM,
    )
    router.initialize()

    engine = router._select_replica()
    assert engine is router._replica_engines[0]["engine"]

    await router.close()


@pytest.mark.asyncio
async def test_read_replica_router_fallback_to_primary_when_no_healthy():
    """Falls back to primary engine when no replicas are healthy."""
    r1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[r1],
    )
    router.initialize()
    router._healthy_replicas.clear()

    engine = router._select_replica()
    assert engine is router._primary_engine

    await router.close()


@pytest.mark.asyncio
async def test_check_replica_health_and_failover():
    """Health check marks failing replicas unhealthy and records status."""
    r1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[r1],
    )
    router.initialize()

    # Healthy test
    health = await router.check_replica_health()
    assert health["replica_0"] == "healthy"
    assert 0 in router._healthy_replicas

    # Simulate replica failure
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=RuntimeError("Replica dead")):
        health_bad = await router.check_replica_health()
        assert "unhealthy" in health_bad["replica_0"]
        assert 0 not in router._healthy_replicas

    await router.close()


@pytest.mark.asyncio
async def test_get_replication_lag():
    """Calculates lag or handles errors gracefully."""
    r1 = ReplicaConfig(url="sqlite+aiosqlite:///:memory:")
    router = ReadReplicaRouter(
        primary_url="sqlite+aiosqlite:///:memory:",
        replicas=[r1],
    )
    router.initialize()

    # Unhealthy replica returns None
    router._replica_engines[0]["healthy"] = False
    lags = await router.get_replication_lag()
    assert lags["replica_0"] is None

    # Healthy replica mock lag
    router._replica_engines[0]["healthy"] = True
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0.42
        mock_exec.return_value = mock_result

        lags = await router.get_replication_lag()
        assert lags["replica_0"] == 0.42

    await router.close()


def test_create_replica_router_from_env(monkeypatch):
    """create_replica_router reads env vars."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://primary:5432/db")
    monkeypatch.setenv(
        "DATABASE_REPLICA_URLS",
        "postgresql+asyncpg://rep1:5432/db, postgresql+asyncpg://rep2:5432/db",
    )
    monkeypatch.setenv("DATABASE_REPLICA_STRATEGY", "random")

    router = create_replica_router()
    assert router.primary_url == "postgresql+asyncpg://primary:5432/db"
    assert len(router.replicas) == 2
    assert router.replicas[0].url == "postgresql+asyncpg://rep1:5432/db"
    assert router.replicas[1].url == "postgresql+asyncpg://rep2:5432/db"
    assert router.strategy == ReplicaStrategy.RANDOM
