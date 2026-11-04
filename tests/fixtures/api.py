"""
API Fixtures - FastAPI app and TestClient.

This is the cornerstone of the new isolated testing setup.
"""

import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# NOTE: No top-level imports from 'src' here!
# This guarantees no application code runs during pytest collection.

# Mock only OpenTelemetry instrumentation to prevent TracerProvider version conflicts.
# Do NOT mock opentelemetry, opentelemetry.sdk, or opentelemetry.sdk.trace because
# chromadb needs the real SDK modules (opentelemetry.sdk.trace.export, etc.).
sys.modules["opentelemetry.instrumentation"] = MagicMock()
sys.modules["opentelemetry.instrumentation.fastapi"] = MagicMock()

# Mock instructor and gemini modules to prevent import errors
# These are used by RouterAgentService but not needed for basic endpoint tests
sys.modules["instructor"] = MagicMock()
sys.modules["instructor.processing"] = MagicMock()
sys.modules["instructor.processing.multimodal"] = MagicMock()
sys.modules["instructor.processing.function_calls"] = MagicMock()
sys.modules["instructor.core"] = MagicMock()
sys.modules["instructor.core.exceptions"] = MagicMock()
sys.modules["instructor.core.patch"] = MagicMock()
sys.modules["instructor.processing.response"] = MagicMock()
sys.modules["instructor.providers"] = MagicMock()
sys.modules["instructor.providers.anthropic"] = MagicMock()
sys.modules["instructor.providers.anthropic.utils"] = MagicMock()
sys.modules["instructor.providers.gemini"] = MagicMock()
sys.modules["instructor.providers.gemini.client"] = MagicMock()
# Do NOT mock 'google' itself - it's a namespace package needed by google.protobuf
# (used by opentelemetry/chromadb). Only mock google.generativeai (Gemini SDK).
sys.modules["google.generativeai"] = MagicMock()

# Disable OpenTelemetry in tests to avoid instrumentation errors
os.environ["OTEL_SDK_DISABLED"] = "true"

# NOTE: No custom event_loop fixture is defined here.
# For pytest-asyncio 0.23+, a custom event_loop fixture conflicts with the
# asyncio_default_fixture_loop_scope setting in pyproject.toml and causes
# "Task got Future attached to a different loop" errors.
# See: https://pytest-asyncio.readthedocs.io/en/latest/reference/changelog.html


@pytest.fixture(scope="function")
async def test_client(async_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    Provides a fully isolated LIGHTWEIGHT test client for each test function.

    This fixture:
    1. Creates a minimal FastAPI app (NO lifespan, NO heavy middleware)
    2. Includes auth and learning routers
    3. Mocks authentication for testing
    4. Each request gets its own session from the engine
    5. Prevents 60+ second hangs from full create_app() lifespan
    """
    from fastapi import FastAPI

    from src.core.api.auth.router import router as auth_router
    from src.core.api.learning_endpoints import router as learning_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database import database as db_module
    from src.core.database.database import get_db

    # Create minimal app - NO lifespan, NO heavy middleware
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(learning_router)

    # Mock authentication - always return a test user
    from types import SimpleNamespace

    async def override_get_current_user():
        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Create session factory bound to SQLite test engine
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Keep legacy get_db dependency paths deterministic in tests.
    previous_engine = db_module.db_manager.engine
    previous_session_maker = db_module.db_manager.async_session_maker
    db_module.db_manager.engine = async_engine
    db_module.db_manager.async_session_maker = session_factory

    # Each request gets its OWN session
    async def override_get_async_session():
        async with session_factory() as session:
            try:
                yield session
            finally:
                # Always commit - changes (via flush) must persist
                # even when the endpoint raises HTTPException (401/429).
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()

    app.dependency_overrides[get_db] = override_get_async_session

    # Use ASGITransport to connect test client to the FastAPI app
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
    db_module.db_manager.engine = previous_engine
    db_module.db_manager.async_session_maker = previous_session_maker


@pytest.fixture(scope="function")
def sync_test_client(db_session) -> Generator:
    """
    Provides a synchronous TestClient for sync tests.

    Used for tests that don't need async (e.g., simple endpoint tests).
    Most new tests should use the async test_client instead.

    Note: Disables OpenTelemetry instrumentation to avoid version conflicts.
    """
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src.core.database.database import get_db
    from src.main import create_test_app

    # Mock OpenTelemetry instrumentation to prevent TracerProvider errors
    with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
        with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"):
            # Create isolated app instance with all routers registered
            app = create_test_app()

        # Override database session dependency
        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            yield client

    # Clean up
    app.dependency_overrides.clear()


# ============================================================================
# POSTGRESQL TEST CLIENT
# ============================================================================


@pytest.fixture(scope="function")
async def postgres_test_client(postgres_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    PostgreSQL-backed test client for production-like testing.

    Uses a LIGHTWEIGHT FastAPI app (no lifespan, no middleware) to avoid
    slow startup from Redis, RabbitMQ, LLM, and circuit breaker init.

    IMPORTANT: Each HTTP request gets its OWN session from the engine.
    This avoids asyncpg's task-affinity restriction (connections can't be
    shared across async tasks). The test assertion session (postgres_session)
    sees committed data via PostgreSQL READ COMMITTED isolation.

    Requires PostgreSQL to be running (docker-compose).
    """
    from fastapi import FastAPI

    from src.core.api.auth.router import router as auth_router
    from src.core.api.learning_endpoints import router as learning_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database import database as db_module
    from src.core.database.database import get_db

    # Create minimal app - NO lifespan, NO heavy middleware
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(learning_router)

    # Mock authentication - always return a test user
    from types import SimpleNamespace

    async def override_get_current_user():
        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Create session factory bound to PostgreSQL test engine
    session_factory = async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Keep legacy get_db dependency paths deterministic in tests.
    previous_engine = db_module.db_manager.engine
    previous_session_maker = db_module.db_manager.async_session_maker
    db_module.db_manager.engine = postgres_engine
    db_module.db_manager.async_session_maker = session_factory

    # Each request gets its OWN session (avoids asyncpg task-affinity issues)
    async def override_get_async_session():
        async with session_factory() as session:
            try:
                yield session
            finally:
                # Always commit - lockout changes (via flush) must persist
                # even when the endpoint raises HTTPException (401/429).
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()

    app.dependency_overrides[get_db] = override_get_async_session

    # Use ASGITransport to connect test client to the FastAPI app
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
    db_module.db_manager.engine = previous_engine
    db_module.db_manager.async_session_maker = previous_session_maker
