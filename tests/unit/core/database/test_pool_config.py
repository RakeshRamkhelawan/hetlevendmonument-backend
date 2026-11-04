"""Unit tests for src.core.database.pool_config."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool

from src.core.database.pool_config import (
    PoolConfig,
    DatabasePool,
    get_db_pool,
    get_db,
    _db_pool,
)
import src.core.database.pool_config as pool_module


def test_pool_config_defaults():
    """Validates default configuration parameters."""
    cfg = PoolConfig()
    assert cfg.pool_size == 10
    assert cfg.max_overflow == 20
    assert cfg.pool_timeout == 30
    assert cfg.pool_recycle == 1800
    assert cfg.pool_pre_ping is True
    assert cfg.echo is False


def test_pool_config_from_env(monkeypatch):
    """Parses environment variables for connection pooling."""
    monkeypatch.setenv("DB_POOL_SIZE", "15")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "30")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "45")
    monkeypatch.setenv("DB_POOL_RECYCLE", "900")
    monkeypatch.setenv("DB_POOL_PRE_PING", "false")
    monkeypatch.setenv("DB_ECHO", "true")

    cfg = PoolConfig.from_env()
    assert cfg.pool_size == 15
    assert cfg.max_overflow == 30
    assert cfg.pool_timeout == 45
    assert cfg.pool_recycle == 900
    assert cfg.pool_pre_ping is False
    assert cfg.echo is True


@pytest.mark.asyncio
async def test_database_pool_create_engine_null_pool():
    """DatabasePool with use_null_pool=True creates engine with NullPool."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    engine = pool.create_engine()
    assert isinstance(engine, AsyncEngine)
    assert engine.pool.__class__.__name__ == "NullPool"
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_engine_property_lazy_creation():
    """Accessing .engine property initializes engine if not created yet."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    assert pool._engine is None
    engine = pool.engine
    assert engine is not None
    assert pool._engine is engine
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_get_session():
    """get_session returns a valid AsyncSession."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    session = pool.get_session()
    assert isinstance(session, AsyncSession)
    await session.close()
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_status_not_initialized():
    """get_pool_status returns not_initialized when engine has not been created."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    status = await pool.get_pool_status()
    assert status == {"status": "not_initialized"}


@pytest.mark.asyncio
async def test_database_pool_status_active():
    """get_pool_status returns active metrics once engine is initialized."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    _ = pool.engine
    status = await pool.get_pool_status()
    assert status["status"] == "active"
    assert "config" in status
    assert status["config"]["pool_size"] == pool.config.pool_size
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_health_check_success():
    """health_check returns True on successful SELECT 1."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    healthy = await pool.health_check()
    assert healthy is True
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_health_check_failure():
    """health_check returns False when query raises exception."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    _ = pool.engine

    with patch.object(pool, "get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.execute.side_effect = RuntimeError("DB down")
        mock_get_session.return_value = mock_session

        healthy = await pool.health_check()
        assert healthy is False
    await pool.close()


@pytest.mark.asyncio
async def test_database_pool_close():
    """Closing database pool disposes engine."""
    pool = DatabasePool("sqlite+aiosqlite:///:memory:", use_null_pool=True)
    _ = pool.engine
    assert pool._engine is not None
    await pool.close()


def test_get_db_pool_singleton(monkeypatch):
    """get_db_pool initializes and caches singleton pool instance."""
    monkeypatch.setattr(pool_module, "_db_pool", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    pool1 = get_db_pool()
    pool2 = get_db_pool()
    assert pool1 is pool2
    assert isinstance(pool1, DatabasePool)


@pytest.mark.asyncio
async def test_get_db_generator_success(monkeypatch):
    """get_db yields session and commits on successful block."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_pool = MagicMock(spec=DatabasePool)
    mock_pool.get_session.return_value = mock_session

    monkeypatch.setattr(pool_module, "get_db_pool", lambda: mock_pool)

    gen = get_db()
    session = await anext(gen)
    assert session is mock_session
    mock_session.__aenter__.assert_awaited_once()

    # Complete generator
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_generator_rollback_on_exception(monkeypatch):
    """get_db catches exception, rolls back session, and re-raises."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_pool = MagicMock(spec=DatabasePool)
    mock_pool.get_session.return_value = mock_session

    monkeypatch.setattr(pool_module, "get_db_pool", lambda: mock_pool)

    gen = get_db()
    session = await anext(gen)
    assert session is mock_session

    with pytest.raises(ValueError, match="Something failed"):
        await gen.athrow(ValueError("Something failed"))

    mock_session.rollback.assert_awaited_once()
