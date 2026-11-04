"""
Comprehensive tests for src/core/database/connection.py
Coverage target: 100% of database connection manager
"""

import os
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from src.core.database.connection import (
    DatabaseManager,
    database_health_check,
    db_manager,
    get_database_session,
    get_sync_db,
    initialize_database,
)


class TestDatabaseManagerInitialization:
    """Test DatabaseManager initialization"""

    def test_initialization(self):
        """Test DatabaseManager initialization"""
        manager = DatabaseManager()

        assert manager.engine is None
        assert manager.session_factory is None
        assert manager._is_initialized is False
        assert isinstance(manager._connection_stats, dict)

    def test_connection_stats_initial_state(self):
        """Test connection stats initial values"""
        manager = DatabaseManager()

        assert manager._connection_stats["total_connections"] == 0
        assert manager._connection_stats["active_connections"] == 0
        assert manager._connection_stats["failed_connections"] == 0
        assert manager._connection_stats["last_error"] is None


class TestGetDatabaseUrl:
    """Test _get_database_url method"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    def test_get_database_url_from_env(self):
        """Test getting database URL from environment"""
        manager = DatabaseManager()

        url = manager._get_database_url()

        assert url == "postgresql://localhost/test"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_database_url_not_set(self):
        """Test getting database URL when not set"""
        manager = DatabaseManager()

        url = manager._get_database_url()

        assert url is None


class TestInitialize:
    """Test initialize method"""

    @patch.dict(os.environ, {}, clear=True)
    def test_initialize_no_database_url(self):
        """Test initialization fails without DATABASE_URL"""
        manager = DatabaseManager()

        result = manager.initialize()

        assert result is False
        assert manager._is_initialized is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    @patch("src.core.database.connection.create_engine")
    @patch("src.core.database.connection.sessionmaker")
    def test_initialize_success(self, mock_sessionmaker, mock_create_engine):
        """Test successful initialization"""
        # Mock engine with proper context manager
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 1
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        # Bypass event listener setup (which requires real engine)
        manager._setup_event_listeners = Mock()
        result = manager.initialize()

        assert result is True
        assert manager._is_initialized is True
        assert manager.engine is not None

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    @patch("src.core.database.connection.create_engine")
    def test_initialize_connection_test_fails(self, mock_create_engine):
        """Test initialization when connection test fails"""
        # Mock engine that fails connection test
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection failed")
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()
        result = manager.initialize()

        assert result is False
        assert manager._is_initialized is False

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    @patch("src.core.database.connection.create_engine")
    def test_initialize_exception_handling(self, mock_create_engine):
        """Test initialization handles exceptions"""
        mock_create_engine.side_effect = Exception("Database error")

        manager = DatabaseManager()
        result = manager.initialize()

        assert result is False
        assert "Database error" in manager._connection_stats["last_error"]


class TestTestConnection:
    """Test _test_connection method"""

    def test_test_connection_success(self):
        """Test successful connection test"""
        manager = DatabaseManager()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 1
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        manager.engine = mock_engine

        result = manager._test_connection()

        assert result is True

    def test_test_connection_wrong_result(self):
        """Test connection test with wrong result"""
        manager = DatabaseManager()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 2  # Not 1
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        manager.engine = mock_engine

        result = manager._test_connection()

        assert result is False

    def test_test_connection_exception(self):
        """Test connection test handles exceptions"""
        manager = DatabaseManager()
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection error")
        manager.engine = mock_engine

        result = manager._test_connection()

        assert result is False


class TestGetSession:
    """Test get_session method"""

    def test_get_session_not_initialized_raises(self):
        """Test get_session raises when not initialized"""
        manager = DatabaseManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            with manager.get_session() as session:
                pass

    @patch("src.core.database.connection.sessionmaker")
    def test_get_session_success(self, mock_sessionmaker):
        """Test successful session retrieval"""
        manager = DatabaseManager()
        manager._is_initialized = True

        mock_session = MagicMock()
        mock_factory = Mock(return_value=mock_session)
        manager.session_factory = mock_factory

        with manager.get_session() as session:
            assert session == mock_session

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("src.core.database.connection.sessionmaker")
    def test_get_session_exception_rolls_back(self, mock_sessionmaker):
        """Test session rollback on exception"""
        manager = DatabaseManager()
        manager._is_initialized = True

        mock_session = MagicMock()
        mock_factory = Mock(return_value=mock_session)
        manager.session_factory = mock_factory

        with pytest.raises(ValueError):
            with manager.get_session() as session:
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestGetSessionDirect:
    """Test get_session_direct method"""

    def test_get_session_direct_not_initialized(self):
        """Test get_session_direct raises when not initialized"""
        manager = DatabaseManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.get_session_direct()

    def test_get_session_direct_success(self):
        """Test successful direct session retrieval"""
        manager = DatabaseManager()
        manager._is_initialized = True

        mock_session = MagicMock()
        mock_factory = Mock(return_value=mock_session)
        manager.session_factory = mock_factory

        session = manager.get_session_direct()

        assert session == mock_session


class TestHealthCheck:
    """Test health_check method"""

    def test_health_check_not_initialized(self):
        """Test health check when not initialized"""
        manager = DatabaseManager()

        health = manager.health_check()

        assert health["status"] == "not_initialized"
        assert health["initialized"] is False

    def test_health_check_healthy(self):
        """Test health check when healthy"""
        manager = DatabaseManager()
        manager._is_initialized = True

        # Mock successful connection test
        with patch.object(manager, "_test_connection", return_value=True):
            mock_engine = MagicMock()
            mock_pool = MagicMock()
            mock_pool.status.return_value = None
            mock_engine.pool = mock_pool
            manager.engine = mock_engine

            health = manager.health_check()

            assert health["status"] == "healthy"
            assert health["initialized"] is True

    def test_health_check_unhealthy(self):
        """Test health check when connection fails"""
        manager = DatabaseManager()
        manager._is_initialized = True

        # Mock failed connection test
        with patch.object(manager, "_test_connection", return_value=False):
            manager.engine = MagicMock()

            health = manager.health_check()

            assert health["status"] == "unhealthy"

    def test_health_check_exception(self):
        """Test health check handles exceptions"""
        manager = DatabaseManager()
        manager._is_initialized = True

        # Mock exception during health check
        with patch.object(manager, "_test_connection", side_effect=Exception("Test error")):
            health = manager.health_check()

            assert health["status"] == "error"
            assert "error" in health


class TestClose:
    """Test close method"""

    def test_close_with_engine(self):
        """Test closing database connections"""
        manager = DatabaseManager()
        mock_engine = MagicMock()
        manager.engine = mock_engine

        manager.close()

        mock_engine.dispose.assert_called_once()

    def test_close_without_engine(self):
        """Test close when no engine exists"""
        manager = DatabaseManager()
        manager.engine = None

        # Should not raise
        manager.close()


class TestGlobalFunctions:
    """Test global convenience functions"""

    @patch("src.core.database.connection.db_manager")
    def test_get_database_session(self, mock_manager):
        """Test get_database_session function"""
        mock_session = MagicMock()

        # Setup context manager properly
        mock_cm = MagicMock()
        mock_cm.__enter__ = Mock(return_value=mock_session)
        mock_cm.__exit__ = Mock(return_value=False)
        mock_manager.get_session.return_value = mock_cm

        # get_database_session is a generator, iterate to get the session
        gen = get_database_session()
        session = next(gen)
        assert session == mock_session

        # Close the generator
        try:
            next(gen)
        except StopIteration:
            pass

    @patch("src.core.database.connection.get_database_session")
    def test_get_sync_db_compatibility(self, mock_get_session):
        """Test get_sync_db legacy compatibility"""
        result = get_sync_db()

        assert result == mock_get_session.return_value

    @patch("src.core.database.connection.db_manager")
    def test_initialize_database(self, mock_manager):
        """Test initialize_database function"""
        mock_manager.initialize.return_value = True

        result = initialize_database()

        assert result is True
        mock_manager.initialize.assert_called_once()

    @patch("src.core.database.connection.db_manager")
    def test_database_health_check(self, mock_manager):
        """Test database_health_check function"""
        mock_health = {"status": "healthy"}
        mock_manager.health_check.return_value = mock_health

        result = database_health_check()

        assert result == mock_health


class TestGlobalInstance:
    """Test global db_manager instance"""

    def test_global_db_manager_exists(self):
        """Test global db_manager instance exists"""
        assert db_manager is not None
        assert isinstance(db_manager, DatabaseManager)


class TestEventListeners:
    """Test event listener setup"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    @patch("src.core.database.connection.create_engine")
    @patch("src.core.database.connection.event")
    def test_event_listeners_registered(self, mock_event, mock_create_engine):
        """Test event listeners are registered"""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        manager = DatabaseManager()

        # Should not raise during initialization
        try:
            manager.initialize()
        except:
            pass  # Ignore other initialization errors

        # Verify event listeners were set up
        assert mock_event.listens_for.called
