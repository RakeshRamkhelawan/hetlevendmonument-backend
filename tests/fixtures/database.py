"""
tests/fixtures/database.py - Database Fixtures

Provides clean, isolated database fixtures using the DI container pattern.
All fixtures use savepoint/rollback for perfect test isolation.

KEY PRINCIPLES:
1. Session-scoped engine (created once, shared for performance)
2. Function-scoped sessions (fresh transaction per test)
3. Savepoint rollback (no cleanup queries needed)
4. No global state (uses DI container overrides)

Created: 2025-12-06
"""

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dependency_injector import providers
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool
from tests.fixtures.testdatabase import (
    TestdatabaseNietOpgegeven,
    eis_testdatabase,
    testdatabase_poort,
    testdatabase_url,
)

# Set TESTING environment variable BEFORE importing models
# This ensures JSONType in models uses SQLite-compatible JSON instead of PostgreSQL JSONB
os.environ["TESTING"] = "1"


# ============================================================================
# ENGINE FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Function-scoped async SQLite engine for unit tests.

    Also configures the global db_manager for the duration of each test
    so that code paths calling db_manager.get_session() hit SQLite instead
    of the real PostgreSQL database.
    """
    # Import Base to ensure all models are registered
    from src.core.database.database import Base

    # Import models to register them with metadata
    try:
        from src.core.models.rbac_models import Role, Tenant, User
    except ImportError:
        pass

    try:
        from src.core.auth.models.account_lockout import AccountLockout
    except ImportError:
        pass

    try:
        from src.core.governance.models import AuditLog
    except ImportError:
        pass

    try:
        from src.core.workflow.models import Workflow, WorkflowExecution
    except ImportError:
        pass

    try:
        from src.core.learning.models import LearningExperience
    except ImportError:
        pass

    try:
        from src.core.conversations.models import Conversation, CVAConversation, UserSession
    except ImportError:
        pass

    try:
        from src.domains.agentic.models import (
            AgentSession,
            Feature,
            PromptTemplate,
            SessionMessage,
            ToolDefinition,
            UserPersona,
        )
    except ImportError:
        pass

    try:
        from src.core.procedures.models import DomainPack, ProcedureExecution, ProcedureMetadata
    except ImportError:
        pass

    try:
        from src.domains.tasks.models import Task
    except ImportError:
        pass

    # Use a unique name per test so each test gets its own isolated in-memory DB.
    # A shared URI (cache=shared, StaticPool) would cause state leakage between
    # tests because commits from one test persisted into the next one.
    _db_name = f"test_{uuid.uuid4().hex}"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:{_db_name}?mode=memory&cache=shared&uri=true",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Save original db_manager state and point it at the test engine
    from src.core.database import database as _db_module

    _orig_engine = _db_module.db_manager.engine
    _orig_session_maker = _db_module.db_manager.async_session_maker
    _orig_initialized = _db_module.db_manager._initialized
    _db_module.db_manager.set_engine(engine)

    yield engine

    # Restore original db_manager state, then dispose the test engine
    _db_module.db_manager.engine = _orig_engine
    _db_module.db_manager.async_session_maker = _orig_session_maker
    _db_module.db_manager._initialized = _orig_initialized
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped database session with automatic rollback.

    Each test gets a fresh session. All changes are rolled back
    after the test completes, ensuring perfect isolation.
    """
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session_with_savepoint(
    async_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Database session with savepoint for nested transaction support.

    Use this for tests that need to test rollback behavior or
    nested transactions. The outer transaction is always rolled back.
    """
    async with async_engine.connect() as conn:
        # Start outer transaction (will be rolled back)
        trans = await conn.begin()

        # Create session bound to this connection
        session = AsyncSession(bind=conn, expire_on_commit=False)

        # Start savepoint (inner transaction)
        await conn.begin_nested()

        yield session

        # Rollback outer transaction (discards all changes)
        await trans.rollback()


# ============================================================================
# CONTAINER OVERRIDE FIXTURES
# ============================================================================


@pytest.fixture
def container_override(async_engine: AsyncEngine):
    """
    Override DI container with test engine.

    This fixture integrates the test database engine with the DI container,
    ensuring all code that uses the container gets the test engine.

    Usage:
        def test_something(container_override, db_session):
            # container now uses test engine
            ...
    """
    from src.core.container import container, reset_container

    # Create test session factory
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Override container providers
    container.database_engine.override(providers.Object(async_engine))
    container.session_factory.override(providers.Object(session_factory))

    yield container

    # Reset overrides
    reset_container()


# ============================================================================
# LEGACY COMPATIBILITY FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def async_session(db_session: AsyncSession) -> AsyncSession:
    """
    DEPRECATED: Use db_session instead.
    Alias for backward compatibility.
    """
    return db_session


@pytest_asyncio.fixture
async def session(db_session: AsyncSession) -> AsyncSession:
    """
    DEPRECATED: Use db_session instead.
    Alias for backward compatibility.
    """
    return db_session


# ============================================================================
# DATABASE UTILITIES
# ============================================================================


@pytest_asyncio.fixture
async def clean_tables(db_session: AsyncSession):
    """
    Clean all tables before test (use sparingly).

    Prefer using savepoint rollback instead of explicit cleanup.
    Only use this for tests that specifically need empty tables.
    """
    # Get all table names
    tables = [
        "workflow_executions",
        "workflows",
        "user_roles",
        "roles",
        "users",
        "tenants",
    ]

    for table in tables:
        try:
            await db_session.execute(text(f"DELETE FROM {table}"))
        except Exception:
            pass  # Table might not exist

    await db_session.commit()

    yield

    # No cleanup needed - session rollback handles it


@pytest.fixture
def db_url() -> str:
    """Get test database URL."""
    return "sqlite+aiosqlite:///file:test_fixtures_db?mode=memory&cache=shared&uri=true"


# ============================================================================
# POSTGRESQL TEST FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def postgres_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Session-scoped PostgreSQL engine for production-like testing.

    Uses actual PostgreSQL database for accurate testing of:
    - Timezone-aware datetime handling
    - JSON/JSONB column types
    - Transaction isolation
    - Concurrent access patterns

    Requires PostgreSQL to be running (e.g., via docker-compose).
    """
    from src.core.database.database import Base

    # Import all models to register them with Base.metadata
    # AuditLog is not imported here: model_registry.register_all_models() covers it
    from src.core.models import (  # noqa: F401
        AccountLockout,
        EvaluationResult,
        Role,
        RolePermission,
        SecurityAlert,
        Tenant,
        UsageRecord,
        User,
    )

    # Import all domain models to register them with Base.metadata
    try:
        from src.domains.tasks.models import Task  # noqa: F401
    except ImportError:
        pass

    # Get PostgreSQL test database URL from environment.
    #
    # LET OP, gemeten 2026-09-15: deze fixture wordt ook door een UNITTEST gebruikt
    # (tests/unit/test_neo_account_lockout_postgres.py) en draait dus mee in de blokkerende
    # poort, waar geen database is aangewezen. Twee dingen daarom:
    #   - de opgave wordt LUI opgehaald. `os.getenv("TEST_DB_URL", testdatabase_url(...))`
    #     evalueert de default altijd, dus die vorm faalde zelfs als TEST_DB_URL wel gezet was.
    #   - zonder aangewezen database SKIPT deze fixture. Dat is geen gok en ook geen stille
    #     terugval naar poort 5455 (ADR-036 OP-243): er is simpelweg niets om tegen te
    #     draaien, en dat is hetzelfde antwoord dat de regel hieronder al gaf toen de
    #     database niet bestond.
    test_db_url = os.getenv("TEST_DB_URL", "").strip()
    if not test_db_url:
        try:
            test_db_url = testdatabase_url(database="sanskriti_test")
        except TestdatabaseNietOpgegeven as exc:
            pytest.skip(f"Geen testdatabase aangewezen voor postgres_engine: {exc}")

    # De opruiming aan het eind doet `DROP SCHEMA public CASCADE`: alleen op een aantoonbare testdatabase (naam op
    # `_test`, niet de ontwikkelpoort 5435). Hier VOORAF geweigerd, niet pas bij de opruiming: een fout bij de
    # start noemt de oorzaak, een stille `except` bij de opruiming niet (brief 2026-10-26).
    eis_testdatabase(test_db_url)

    engine = create_async_engine(
        test_db_url,
        echo=False,
        poolclass=NullPool,
    )

    # Create all tables (skip gracefully if DB does not exist)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        await engine.dispose()
        pytest.skip(f"PostgreSQL test database not available: {e}")

    yield engine

    # Drop all tables (ignore errors from unnamed constraints)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    except Exception:
        pass  # Best-effort cleanup

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def postgres_session(
    postgres_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped PostgreSQL session for production-like testing.

    Each test gets its own session. Changes are NOT rolled back because:
    - UserFactory.create_user() calls commit() (needed for FK integrity)
    - Each test creates unique data with UUID-based identifiers
    - No test data conflicts between tests
    - Full table cleanup happens at engine teardown
    """
    session_factory = async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        # Rollback any uncommitted changes (flushed but not committed)
        await session.rollback()
