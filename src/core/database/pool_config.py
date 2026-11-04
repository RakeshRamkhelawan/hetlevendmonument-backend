"""
SD-2.1: Database Connection Pooling Configuration
Configures SQLAlchemy async connection pooling.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Union
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Database pool configuration."""

    pool_size: int = 10  # Number of connections to keep open
    max_overflow: int = 20  # Additional connections when pool is exhausted
    pool_timeout: int = 30  # Seconds to wait for connection
    pool_recycle: int = 1800  # Recycle connections after 30 min
    pool_pre_ping: bool = True  # Check connection health before use
    echo: bool = False  # Log SQL statements

    @classmethod
    def from_env(cls) -> "PoolConfig":
        """Create config from environment variables."""
        return cls(
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
            pool_pre_ping=os.getenv("DB_POOL_PRE_PING", "true").lower() == "true",
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )


class DatabasePool:
    """
    SD-2.1: Managed database connection pool.

    Features:
    - Configurable pool size
    - Connection health checks
    - Automatic connection recycling
    - Metrics and monitoring
    """

    def __init__(
        self,
        database_url: str,
        config: PoolConfig | None = None,
        use_null_pool: bool = False,
    ) -> None:
        self.database_url = database_url
        self.config = config or PoolConfig.from_env()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._use_null_pool = use_null_pool

    def create_engine(self) -> AsyncEngine:
        """Create the async engine with pooling."""
        # Choose pool class
        pool_class: type[NullPool] | type[AsyncAdaptedQueuePool]
        if self._use_null_pool:
            # No pooling - useful for testing
            pool_class = NullPool
            pool_kwargs: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        else:
            pool_class = AsyncAdaptedQueuePool
            pool_kwargs = {
                "pool_size": self.config.pool_size,
                "max_overflow": self.config.max_overflow,
                "pool_timeout": self.config.pool_timeout,
                "pool_recycle": self.config.pool_recycle,
                "pool_pre_ping": self.config.pool_pre_ping,
            }

        self._engine = create_async_engine(
            self.database_url,
            echo=self.config.echo,
            poolclass=pool_class,
            **pool_kwargs,
        )

        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

        logger.info(
            f"Database pool created: size={self.config.pool_size}, "
            f"max_overflow={self.config.max_overflow}"
        )

        return self._engine

    @property
    def engine(self) -> AsyncEngine | None:
        """Get or create the engine."""
        if self._engine is None:
            self.create_engine()
        return self._engine

    def get_session(self) -> AsyncSession:
        """Get a new session from the pool."""
        if self._session_factory is None:
            self.create_engine()
        if self._session_factory is None:
            raise RuntimeError("Session factory not initialized")
        return self._session_factory()

    async def get_pool_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current pool status and metrics."""
        if self._engine is None:
            return {"status": "not_initialized"}

        pool = self._engine.pool

        return {
            "status": "active",
            "size": (
                getattr(pool, "size", lambda: None)()
                if callable(getattr(pool, "size", None))
                else getattr(pool, "size", None)
            ),
            "checked_in": (
                getattr(pool, "checkedin", lambda: None)()
                if callable(getattr(pool, "checkedin", None))
                else getattr(pool, "checkedin", None)
            ),
            "checked_out": (
                getattr(pool, "checkedout", lambda: None)()
                if callable(getattr(pool, "checkedout", None))
                else getattr(pool, "checkedout", None)
            ),
            "overflow": (
                getattr(pool, "overflow", lambda: None)()
                if callable(getattr(pool, "overflow", None))
                else getattr(pool, "overflow", None)
            ),
            "config": {
                "pool_size": self.config.pool_size,
                "max_overflow": self.config.max_overflow,
                "pool_timeout": self.config.pool_timeout,
                "pool_recycle": self.config.pool_recycle,
            },
        }

    async def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            async with self.get_session() as session:
                from sqlalchemy import text

                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the connection pool."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database pool closed")


# Singleton pool instance
_db_pool: DatabasePool | None = None


def get_db_pool() -> DatabasePool:
    """Get the database pool singleton."""
    global _db_pool
    if _db_pool is None:
        db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/sanskriti")
        _db_pool = DatabasePool(db_url)
    return _db_pool


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency for getting a database session."""
    pool = get_db_pool()
    async with pool.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
