"""Unit tests for src.core.database.health."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.database.health import check_db_connection, get_db_stats


@pytest.mark.asyncio
async def test_check_db_connection_success():
    """Returns True when database session can execute query."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        result = await check_db_connection(session)
        assert result is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_check_db_connection_failure():
    """Returns False when database query raises an exception."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = ConnectionError("Database disconnected")

    result = await check_db_connection(mock_session)
    assert result is False


@pytest.mark.asyncio
async def test_get_db_stats_success():
    """Returns connection status and version string on success."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar.return_value = "PostgreSQL 16.1 on x86_64"
    mock_session.execute.return_value = mock_result

    stats = await get_db_stats(mock_session)
    assert stats["connected"] is True
    assert stats["version"] == "PostgreSQL 16.1 on x86_64"


@pytest.mark.asyncio
async def test_get_db_stats_failure():
    """Returns connected=False and error message when query fails."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = RuntimeError("Connection timeout")

    stats = await get_db_stats(mock_session)
    assert stats["connected"] is False
    assert "Connection timeout" in stats["error"]
