"""
Production PostgreSQL Database Connection Manager
Enterprise-grade connection pooling and session management
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Optional
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from src.core.shared.production_logging import SafeLogger

# Setup logging
logger = logging.getLogger(__name__)
safe_logger = SafeLogger(__name__)


class DatabaseManager:
    """
    Production-ready PostgreSQL database manager
    Features: Connection pooling, health monitoring, failover handling
    """

    def __init__(self) -> None:
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None
        self._is_initialized = False
        self._connection_stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "last_error": None,
        }

    def initialize(self) -> bool:
        """Initialize database connection with production settings"""
        try:
            database_url = self._get_database_url()
            if not database_url:
                safe_logger.error("[CRITICAL] DATABASE_URL not configured")
                return False

            # Create engine with connection pooling
            self.engine = create_engine(
                database_url,
                # Connection Pool Settings
                poolclass=QueuePool,
                pool_size=20,  # Base connections
                max_overflow=30,  # Additional connections
                pool_timeout=30,  # Wait time for connection
                pool_recycle=3600,  # Recycle connections every hour
                pool_pre_ping=True,  # Validate connections before use
                # PostgreSQL specific settings
                echo=os.getenv("DEBUG", "false").lower() == "true",
                echo_pool=False,  # Set to True for pool debugging
                # Connection arguments - removed incompatible parameters
                connect_args={},
            )

            # Setup event listeners for monitoring
            self._setup_event_listeners()

            # Create session factory
            self.session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,  # Keep objects available after commit
            )

            # Test connection
            if self._test_connection():
                self._is_initialized = True
                safe_logger.info("[SUCCESS] Database connection initialized with pooling")
                return True
            else:
                safe_logger.error("[FAILED] Database connection test failed")
                return False

        except Exception as e:
            safe_logger.error(f"[ERROR] Database initialization failed: {e}")
            self._connection_stats["last_error"] = str(e)
            return False

    def _get_database_url(self) -> str | None:
        """Get database URL from environment"""
        db_url = os.getenv("DATABASE_URL")
        return db_url

    def _setup_event_listeners(self) -> None:
        """Setup SQLAlchemy event listeners for monitoring"""
        if self.engine is None:
            return

        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_connection: Any, connection_record: Any) -> None:  # TODO(TYPE): replace Any with concrete type
            self._connection_stats["total_connections"] += 1
            self._connection_stats["active_connections"] += 1
            logger.debug(
                f"New database connection established. Active: {self._connection_stats['active_connections']}"
            )

        @event.listens_for(self.engine, "close")
        def receive_close(dbapi_connection: Any, connection_record: Any) -> None:  # TODO(TYPE): replace Any with concrete type
            self._connection_stats["active_connections"] = max(
                0, self._connection_stats["active_connections"] - 1
            )
            logger.debug(
                f"Database connection closed. Active: {self._connection_stats['active_connections']}"
            )

        @event.listens_for(self.engine, "handle_error")
        def receive_error(exception_context: Any) -> None:  # TODO(TYPE): replace Any with concrete type
            self._connection_stats["failed_connections"] += 1
            self._connection_stats["last_error"] = str(exception_context.original_exception)
            logger.error(f"Database error: {exception_context.original_exception}")

    def _test_connection(self) -> bool:
        """Test database connection"""
        if self.engine is None:
            return False
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).scalar()
                return result == 1
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get database session with automatic cleanup
        Usage:
            with db_manager.get_session() as session:
                # Use session here
        """
        if not self._is_initialized or self.session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def get_session_direct(self) -> Session:
        """
        Get database session for dependency injection
        Note: Caller must handle session lifecycle
        """
        if not self._is_initialized or self.session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.session_factory()

    def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Comprehensive database health check"""
        health_info = {
            "status": "unknown",
            "initialized": self._is_initialized,
            "connection_stats": self._connection_stats.copy(),
            "pool_status": {},
            "last_check": None,
        }

        if not self._is_initialized:
            health_info["status"] = "not_initialized"
            return health_info

        try:
            # Test connection
            connection_ok = self._test_connection()

            # Get pool information
            if self.engine is not None and hasattr(self.engine.pool, "status"):
                self.engine.pool.status()
                health_info["pool_status"] = {
                    "pool_size": getattr(self.engine.pool, "size", 0),
                    "checked_in": getattr(self.engine.pool, "checkedin", 0),
                    "checked_out": getattr(self.engine.pool, "checkedout", 0),
                    "overflow": getattr(self.engine.pool, "overflow", 0),
                }

            health_info["status"] = "healthy" if connection_ok else "unhealthy"

        except Exception as e:
            health_info["status"] = "error"
            health_info["error"] = str(e)
            logger.error(f"Health check failed: {e}")

        return health_info

    def close(self) -> None:
        """Close all database connections"""
        if self.engine is not None:
            self.engine.dispose()
            safe_logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


# FastAPI dependency
def get_database_session() -> Generator[Session, None, None]:
    """FastAPI dependency to get database session"""
    with db_manager.get_session() as session:
        yield session


# Legacy compatibility function
def get_sync_db() -> Generator[Session, None, None]:
    """Legacy compatibility - use get_database_session instead"""
    return get_database_session()


# Initialization function
def initialize_database() -> bool:
    """Initialize database connection - call during startup"""
    return db_manager.initialize()


# Health check function
def database_health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get database health status"""
    return db_manager.health_check()
