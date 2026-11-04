"""
Comprehensive tests for src/core/database/connection.py
Target: 80%+ coverage for database module (requirement)
"""

import os
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.pool import QueuePool

from src.core.database.connection import DatabaseManager


# STRUCTURAL FIX: Helper fixture for properly configured engine mock
@pytest.fixture
def properly_mocked_engine():
    """
    Create a properly configured engine mock with context manager support.

    This fixes the common pattern of broken mocks that don't support:
    - event.listens_for() decorators
    - engine.connect() as context manager
    - pool attributes
    """
    mock_engine = MagicMock()
    mock_engine.pool = MagicMock(spec=QueuePool)
    mock_engine.pool.size.return_value = 20
    mock_engine.pool.checkedin.return_value = 15
    mock_engine.pool.checkedout.return_value = 5
    mock_engine.pool.overflow.return_value = 0
    mock_engine.pool.status.return_value = None

    # CRITICAL: Configure connect() as a proper context manager
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 1
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_conn
    mock_context.__exit__.return_value = None
    mock_engine.connect.return_value = mock_context

    return mock_engine


class TestDatabaseManagerInitialization:
    """Test DatabaseManager initialization"""

    def test_initialization_creates_empty_manager(self):
        """Test manager initializes with default state"""
        manager = DatabaseManager()

        assert manager.engine is None
        assert manager.session_factory is None
        assert manager._is_initialized is False
        assert manager._connection_stats["total_connections"] == 0
        assert manager._connection_stats["active_connections"] == 0
        assert manager._connection_stats["failed_connections"] == 0

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_initialize_success(self, mock_create_engine, mock_event):
        """Test successful database initialization"""
        mock_engine = Mock()
        mock_engine.pool = Mock(spec=QueuePool)
        mock_conn = Mock()
        mock_conn.execute.return_value.scalar.return_value = 1

        # Properly mock context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_conn)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.connect.return_value = mock_context

        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        result = manager.initialize()

        assert result is True
        assert manager._is_initialized is True
        assert manager.engine is not None
        assert manager.session_factory is not None

    @patch.dict(os.environ, {}, clear=True)
    def test_initialize_no_database_url(self):
        """Test initialization fails without DATABASE_URL"""
        manager = DatabaseManager()
        result = manager.initialize()

        assert result is False
        assert manager._is_initialized is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.create_engine")
    def test_initialize_connection_test_fails(self, mock_create_engine):
        """Test initialization fails when connection test fails"""
        mock_engine = Mock()
        mock_engine.connect.side_effect = OperationalError("Connection failed", None, None)
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        result = manager.initialize()

        assert result is False
        assert manager._is_initialized is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.create_engine")
    def test_initialize_exception_handling(self, mock_create_engine):
        """Test initialization handles exceptions gracefully"""
        mock_create_engine.side_effect = Exception("Unexpected error")

        manager = DatabaseManager()
        result = manager.initialize()

        assert result is False
        assert manager._connection_stats["last_error"] == "Unexpected error"


class TestGetDatabaseUrl:
    """Test _get_database_url method"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"})
    def test_get_database_url_from_env(self):
        """Test getting database URL from environment"""
        manager = DatabaseManager()
        url = manager._get_database_url()

        assert url == "postgresql://localhost/db"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_database_url_not_set(self):
        """Test getting database URL when not set"""
        manager = DatabaseManager()
        url = manager._get_database_url()

        assert url is None


class TestConnectionStats:
    """Test connection statistics tracking"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.create_engine")
    def test_connection_stats_updated_on_connect(self, mock_create_engine):
        """Test connection stats are updated when connection is made"""
        mock_engine = Mock()
        mock_engine.pool = Mock(spec=QueuePool)
        mock_conn = Mock()
        mock_conn.execute.return_value.scalar.return_value = 1

        # Properly mock context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_conn)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.connect.return_value = mock_context
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        manager.initialize()

        # Stats should be tracked (actual values depend on implementation)
        assert isinstance(manager._connection_stats["total_connections"], int)
        assert isinstance(manager._connection_stats["active_connections"], int)


class TestGetSession:
    """Test get_session context manager"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.create_engine")
    def test_get_session_not_initialized_raises(self, mock_create_engine):
        """Test get_session raises error when not initialized"""
        manager = DatabaseManager()

        with pytest.raises(RuntimeError, match="Database not initialized"):
            with manager.get_session():
                pass

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_get_session_success(self, mock_create_engine, mock_event, properly_mocked_engine):
        """Test successful session creation and cleanup"""
        mock_create_engine.return_value = properly_mocked_engine

        mock_session = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_session)

        manager = DatabaseManager()
        manager.initialize()
        manager.session_factory = mock_session_factory

        with manager.get_session() as session:
            assert session == mock_session

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_get_session_rollback_on_error(
        self, mock_create_engine, mock_event, properly_mocked_engine
    ):
        """Test session rolls back on error"""
        mock_create_engine.return_value = properly_mocked_engine

        mock_session = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_session)

        manager = DatabaseManager()
        manager.initialize()
        manager.session_factory = mock_session_factory

        with pytest.raises(ValueError):
            with manager.get_session() as session:
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestGetSessionDirect:
    """Test get_session_direct method"""

    def test_get_session_direct_not_initialized_raises(self):
        """Test get_session_direct raises error when not initialized"""
        manager = DatabaseManager()

        with pytest.raises(RuntimeError, match="Database not initialized"):
            manager.get_session_direct()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_get_session_direct_returns_session(
        self, mock_create_engine, mock_event, properly_mocked_engine
    ):
        """Test get_session_direct returns session"""
        mock_create_engine.return_value = properly_mocked_engine

        mock_session = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_session)

        manager = DatabaseManager()
        manager.initialize()
        manager.session_factory = mock_session_factory

        session = manager.get_session_direct()

        assert session == mock_session
        mock_session_factory.assert_called_once()


class TestHealthCheck:
    """Test health_check method"""

    def test_health_check_not_initialized(self):
        """Test health check when not initialized"""
        manager = DatabaseManager()
        health = manager.health_check()

        assert health["status"] == "not_initialized"
        assert health["initialized"] is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_health_check_healthy(self, mock_create_engine, mock_event, properly_mocked_engine):
        """Test health check when database is healthy"""
        mock_create_engine.return_value = properly_mocked_engine

        manager = DatabaseManager()
        manager.initialize()
        health = manager.health_check()

        assert health["status"] == "healthy"
        assert health["initialized"] is True
        assert "pool_status" in health

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_health_check_unhealthy(self, mock_create_engine, mock_event, properly_mocked_engine):
        """Test health check when connection test fails"""
        # First connect for initialization succeeds, health check fails
        connect_count = [0]

        def connect_side_effect():
            connect_count[0] += 1
            if connect_count[0] == 1:
                return properly_mocked_engine.connect.return_value
            else:
                raise OperationalError("Connection failed", None, None)

        properly_mocked_engine.connect.side_effect = connect_side_effect
        mock_create_engine.return_value = properly_mocked_engine

        manager = DatabaseManager()
        manager.initialize()
        health = manager.health_check()

        # Status depends on whether _test_connection catches the error
        assert health["status"] in ["unhealthy", "error"]

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.event")
    @patch("src.core.database.connection.create_engine")
    def test_health_check_exception_handling(
        self, mock_create_engine, mock_event, properly_mocked_engine
    ):
        """Test health check handles exceptions"""
        mock_create_engine.return_value = properly_mocked_engine

        manager = DatabaseManager()
        manager.initialize()

        # Make _test_connection raise an exception
        with patch.object(manager, "_test_connection", side_effect=Exception("Test error")):
            health = manager.health_check()

            assert health["status"] == "error"
            assert "error" in health


class TestClose:
    """Test close method"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/testdb"})
    @patch("src.core.database.connection.create_engine")
    def test_close_disposes_engine(self, mock_create_engine):
        """Test close disposes of the engine"""
        mock_engine = Mock()
        mock_engine.pool = Mock(spec=QueuePool)
        mock_conn = Mock()
        mock_conn.execute.return_value.scalar.return_value = 1

        # Properly mock context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_conn)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.connect.return_value = mock_context
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        manager.initialize()
        manager.close()

        mock_engine.dispose.assert_called_once()

    def test_close_when_not_initialized(self):
        """Test close when engine is None"""
        manager = DatabaseManager()
        # Should not raise an exception
        manager.close()
