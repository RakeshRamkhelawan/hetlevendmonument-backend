"""
Dependency Injection Container - Single Source of Truth for Dependencies

This module implements the Dependency Injection pattern using dependency-injector library.
It eliminates global state and provides clean, testable dependencies throughout the application.

ARCHITECTURE BENEFITS:
- No global singletons (eliminates db_manager global state)
- Easy to override for testing (container.database_engine.override())
- Clear dependency graph
- Thread/async safe by design
- Eliminates ContextVar propagation issues

Usage in Production:
    from src.core.container import container
    container.init_resources()

    # Access dependencies
    async with container.database_manager().get_session() as session:
        ...

Usage in Tests:
    from src.core.container import container
    from dependency_injector import providers

    # Override for testing
    container.database_engine.override(providers.Object(test_engine))

    yield

    container.database_engine.reset_override()

Created: 2025-12-06
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Optional
from collections.abc import AsyncGenerator, Callable

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.core.database.unit_of_work import SQLAlchemyUnitOfWork
from src.core.storage.tenant_storage import LocalTenantStorage

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION PROVIDER
# ============================================================================


class DatabaseConfig:
    """Database configuration - can be overridden for testing."""

    def __init__(
        self,
        url: str | None = None,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
    ) -> None:
        # SECURITY FIX: In production, require DATABASE_URL to be set
        # Don't fall back to SQLite which could lead to data loss
        environment = os.getenv("ENVIRONMENT", "development").lower()
        db_url = url or os.getenv("DATABASE_URL")

        if not db_url:
            if environment == "production":
                raise ValueError(
                    "DATABASE_URL environment variable is required in production. "
                    "SQLite fallback is not allowed for security reasons."
                )
            # Development/testing only: fall back to SQLite
            db_url = "sqlite+aiosqlite:///./sanskriti_setu.db"
            logger.warning("DATABASE_URL not set - using SQLite for development/testing only")

        self.url = db_url
        self.echo = echo or os.getenv("DB_ECHO", "false").lower() == "true"
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.url.lower()


class AppConfig:
    """Application configuration."""

    def __init__(
        self,
        app_name: str = "SanskritiSetu",
        version: str = "2.0.0",
        debug: bool = False,
        testing: bool = False,
    ) -> None:
        self.app_name = app_name
        self.version = version
        self.debug = debug or os.getenv("DEBUG", "false").lower() == "true"
        self.testing = testing or os.getenv("TESTING", "false").lower() == "true"


# ============================================================================
# DATABASE ENGINE FACTORY
# ============================================================================


def create_database_engine(config: DatabaseConfig) -> AsyncEngine:
    """
    Factory function to create SQLAlchemy async engine.

    Handles SQLite (testing) vs PostgreSQL (production) differences:
    - SQLite: NullPool (no connection pooling, single-threaded)
    - PostgreSQL: QueuePool with connection pooling
    """
    if config.is_sqlite:
        # SQLite configuration for testing
        engine = create_async_engine(
            config.url,
            echo=config.echo,
            poolclass=NullPool,  # SQLite doesn't support connection pooling
            connect_args={"check_same_thread": False},
        )
        logger.info(f"Created SQLite engine: {config.url}")
    else:
        # PostgreSQL configuration for production
        engine = create_async_engine(
            config.url,
            echo=config.echo,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=config.pool_pre_ping,
        )
        logger.info(f"Created PostgreSQL engine with pool_size={config.pool_size}")

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory with proper settings."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # CRITICAL: Prevents detached instance issues
        autocommit=False,
        autoflush=False,
    )


# ============================================================================
# DATABASE MANAGER (Stateless - uses injected dependencies)
# ============================================================================


class DatabaseManager:
    """
    Stateless database manager - receives dependencies via DI.

    Unlike the old singleton pattern, this class:
    - Has no global state
    - Receives engine/session_factory via constructor
    - Can be easily tested with different engines
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session with automatic cleanup.

        Usage:
            async with db_manager.get_session() as session:
                result = await session.execute(query)
        """
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            from sqlalchemy import text

            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def dispose(self) -> None:
        """Dispose of engine connections."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database engine disposed")


# ============================================================================
# TENANT CONTEXT (Request-Scoped - replaces ContextVar pattern)
# ============================================================================


class TenantContext:
    """
    Request-scoped tenant context - injected as FastAPI dependency.

    This replaces the ContextVar pattern which has propagation issues
    across TestClient HTTP boundaries.

    Benefits:
    - Explicit data flow (no hidden global state)
    - Easy to override in tests
    - Works correctly with TestClient
    - Type-safe and IDE-friendly

    Usage in endpoints:
        @router.get("/users")
        async def list_users(
            tenant: TenantContext = Depends(get_tenant_context),
            db: AsyncSession = Depends(get_db),
        ):
            query = select(User).where(User.tenant_id == tenant.tenant_id)
    """

    def __init__(
        self,
        tenant_id: int | None = None,
        tenant_slug: str | None = None,
        bypass_filter: bool = False,
    ) -> None:
        self._tenant_id = tenant_id
        self._tenant_slug = tenant_slug
        self._bypass_filter = bypass_filter

    @property
    def tenant_id(self) -> int | None:
        return self._tenant_id

    @property
    def tenant_slug(self) -> str | None:
        return self._tenant_slug

    @property
    def bypass_filter(self) -> bool:
        return self._bypass_filter

    @property
    def is_set(self) -> bool:
        return self._tenant_id is not None

    def require_tenant(self) -> int:
        """Get tenant_id or raise if not set."""
        if self._tenant_id is None:
            raise ValueError("Tenant context not set - authentication required")
        return self._tenant_id

    def __repr__(self) -> str:
        return f"TenantContext(tenant_id={self._tenant_id}, bypass={self._bypass_filter})"


# ============================================================================
# DEPENDENCY INJECTION CONTAINER
# ============================================================================


class Container(containers.DeclarativeContainer):
    """
    Main DI Container - Single source of truth for all dependencies.

    Override pattern for testing:
        container = Container()
        container.database_config.override(providers.Object(test_config))
        container.database_engine.override(providers.Object(test_engine))
    """

    # This is now handled dynamically in the app factory
    wiring_config = containers.WiringConfiguration()

    # ========== Configuration ==========
    database_config = providers.Singleton(DatabaseConfig)
    app_config = providers.Singleton(AppConfig)

    # ========== Database Layer ==========
    database_engine = providers.Singleton(
        create_database_engine,
        config=database_config,
    )

    session_factory = providers.Singleton(
        create_session_factory,
        engine=database_engine,
    )

    database_manager = providers.Factory(
        DatabaseManager,
        engine=database_engine,
        session_factory=session_factory,
    )

    # ========== Request-Scoped (created per request) ==========
    tenant_context = providers.Factory(
        TenantContext,
    )

    # ========== Storage Layer ==========
    tenant_storage = providers.Singleton(
        LocalTenantStorage,
        base_path=providers.Callable(
            lambda: os.getenv("STORAGE_BASE_PATH", "./storage/tenant_data")
        ),
    )

    # ========== Unit of Work ==========
    unit_of_work = providers.Factory(
        SQLAlchemyUnitOfWork,
        session_factory=session_factory,
        auto_commit=False,
    )

    # ========== Company Layer Services ==========
    # Note: CompanyService is imported lazily to avoid circular imports
    @staticmethod
    def _create_company_service(
        db_manager: DatabaseManager, tenant_context: TenantContext
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        from src.core.company.company_service import CompanyService

        return CompanyService(db_manager, tenant_context)

    company_service = providers.Factory(
        _create_company_service,
        db_manager=database_manager,
        tenant_context=tenant_context,
    )

    @staticmethod
    def _create_pack_activation_scorer() -> Any:  # TODO(TYPE): replace Any with concrete type
        from src.core.company.pack_activation import PackActivationScorer

        return PackActivationScorer()

    pack_activation_scorer = providers.Singleton(_create_pack_activation_scorer)

    @staticmethod
    def _create_goal_alignment_validator() -> Any:  # TODO(TYPE): replace Any with concrete type
        from src.core.company.goal_alignment import GoalAlignmentValidator

        return GoalAlignmentValidator()

    goal_alignment_validator = providers.Singleton(_create_goal_alignment_validator)

    # ========== Domain Pack Registry ==========
    domain_pack_registry: providers.Singleton[Any] = (  # TODO(TYPE): replace Any with concrete type
        providers.Singleton(  # TODO(TYPE): replace Any with concrete type
            "src.core.procedures.domain_pack_registry.DomainPackRegistry",
            db_manager=database_manager,
        )
    )

    # ========== CVA Cache Provider ==========
    cva_agent_cache: providers.Singleton[Any] = (  # TODO(TYPE): replace Any with concrete type
        providers.Singleton(  # TODO(TYPE): replace Any with concrete type
            "src.core.services.cva_cache_provider.CvaAgentCacheProvider",
            maxsize=100,
            ttl=3600,
        )
    )

    @staticmethod
    def _create_department_service(
        db_manager: DatabaseManager,
        tenant_context: TenantContext,
        pack_registry: object,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        from src.core.company.department_service import DepartmentService

        return DepartmentService(db_manager, tenant_context, pack_registry)

    department_service = providers.Factory(
        _create_department_service,
        db_manager=database_manager,
        tenant_context=tenant_context,
        pack_registry=domain_pack_registry,
    )

    # ========== AI Features (Fase 3.2 DI Migration) ==========
    @staticmethod
    def _create_adaptive_learning_engine() -> Any:  # TODO(TYPE): replace Any with concrete type
        # NOTE: create_adaptive_learning_engine is async; providers.Factory returns the coroutine.
        # Pre-existing pattern via ai_features_endpoints stub. TODO(SP-DSM-007): migrate to providers.Coroutine.
        from src.core.ai.adaptive_learning_engine import create_adaptive_learning_engine

        return create_adaptive_learning_engine()

    @staticmethod
    def _create_intelligent_router() -> Any:  # TODO(TYPE): replace Any with concrete type
        # NOTE: Same pre-existing async pattern. TODO(SP-DSM-007): migrate to providers.Coroutine.
        from src.core.ai.intelligent_routing import create_intelligent_router

        return create_intelligent_router()

    @staticmethod
    def _create_predictive_analytics() -> Any:  # TODO(TYPE): replace Any with concrete type
        # NOTE: Same pre-existing async pattern. TODO(SP-DSM-007): migrate to providers.Coroutine.
        from src.core.ai.predictive_analytics import create_predictive_analytics_engine

        return create_predictive_analytics_engine()

    adaptive_learning_engine = providers.Factory(_create_adaptive_learning_engine)
    intelligent_router = providers.Factory(_create_intelligent_router)
    predictive_analytics = providers.Factory(_create_predictive_analytics)


# ============================================================================
# GLOBAL CONTAINER INSTANCE
# ============================================================================

_container_instance: Container | None = None


def get_container() -> Container:
    """
    Returns a singleton instance of the DI container.
    Initializes the container on first call.
    """
    global _container_instance
    if _container_instance is None:
        _container_instance = Container()
    return _container_instance


# Global container instance for convenience
container = get_container()


# ============================================================================
# FASTAPI DEPENDENCY FUNCTIONS
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    container = get_container()
    db_manager = container.database_manager()
    async with db_manager.get_session() as session:
        yield session


async def get_database_manager() -> DatabaseManager:
    """FastAPI dependency for DatabaseManager instance."""
    container = get_container()
    return container.database_manager()


def get_tenant_context(
    tenant_id: int | None = None,
    bypass: bool = False,
) -> TenantContext:
    """
    Factory for TenantContext - typically called from middleware.

    In production, middleware extracts tenant_id from JWT and creates context.
    In tests, override this dependency directly.
    """
    return TenantContext(tenant_id=tenant_id, bypass_filter=bypass)


# ============================================================================
# LEGACY COMPATIBILITY LAYER
# ============================================================================

# These functions maintain backward compatibility with existing code
# that uses the old db_manager singleton pattern.
#
# DEPRECATION NOTICE: These will be removed in v3.0
# Migrate to: from core.container import container, get_db


async def initialize_database() -> bool:
    """
    DEPRECATED: Database is initialized lazily by the container.

    For explicit initialization, use:
        from src.core.container import container
        engine = container.database_engine()
    """
    logger.warning("initialize_database() is deprecated - container initializes lazily")
    try:
        engine = container.database_engine()
        return engine is not None
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


async def close_database() -> None:
    """DEPRECATED: Use container.database_manager().dispose() instead."""
    logger.warning("close_database() is deprecated")
    try:
        db_manager = container.database_manager()
        await db_manager.dispose()
    except Exception as e:
        logger.error(f"Database close failed: {e}")


# ============================================================================
# INITIALIZATION HELPERS
# ============================================================================


def init_container(
    database_url: str | None = None,
    testing: bool = False,
    echo: bool = False,
) -> Container:
    """
    Initialize container with custom configuration.

    Args:
        database_url: Custom database URL (overrides env var)
        testing: Enable testing mode
        echo: Enable SQL echo logging

    Returns:
        Configured container instance
    """
    cont = get_container()
    if database_url:
        cont.database_config.override(providers.Object(DatabaseConfig(url=database_url, echo=echo)))

    if testing:
        cont.app_config.override(providers.Object(AppConfig(testing=True, debug=True)))

    return cont


def reset_container() -> None:
    """
    Reset all container overrides - call in test teardown.
    """
    cont = get_container()
    cont.database_config.reset_override()
    cont.app_config.reset_override()
    cont.database_engine.reset_override()
    cont.session_factory.reset_override()
    cont.database_manager.reset_override()
    cont.tenant_context.reset_override()
    cont.tenant_storage.reset_override()
    cont.cva_agent_cache.reset_override()
    logger.debug("Container overrides reset")
