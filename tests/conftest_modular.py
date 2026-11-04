"""
tests/conftest_modular.py - Modular Fixture Hub

This is the NEW recommended conftest pattern. It imports fixtures from
the modular tests/fixtures/ package instead of defining everything inline.

MIGRATION GUIDE:
1. New tests should use: from tests.fixtures import *
2. Existing tests continue to work with tests/conftest.py
3. Gradually migrate tests to use modular fixtures
4. Eventually replace conftest.py with this file

BENEFITS:
- Single source of truth for each fixture type
- Easy to maintain and test fixtures independently
- Clear separation of concerns
- No 1800-line conftest files

Usage:
    # In your test file
    from tests.fixtures.database import db_session
    from tests.fixtures.auth import test_user, test_token
    from tests.fixtures.mocks import mock_redis_client
    from tests.fixtures.tenant import test_tenant, tenant_context

Created: 2025-12-06
"""

import pytest

# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (require services)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full stack)")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")
    config.addinivalue_line("markers", "security: Security-related tests")


# ============================================================================
# SESSION-LEVEL FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


# ============================================================================
# AUTOUSE FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_container():
    """
    Reset DI container overrides after each test.

    This ensures no test pollutes the container state for subsequent tests.
    """
    yield

    try:
        from src.core.container import reset_container as do_reset

        do_reset()
    except ImportError:
        pass  # Container not available


@pytest.fixture(autouse=True)
def isolate_tenant_context():
    """
    Clear tenant context after each test.

    Ensures no tenant context leaks between tests.
    """
    yield

    try:
        from src.core.middleware.tenant_context import clear_tenant_context

        clear_tenant_context()
    except ImportError:
        pass  # Module not available


# ============================================================================
# APPLICATION FIXTURES
# ============================================================================


@pytest.fixture
def app(db_session, mock_redis_client, mock_email_service):
    """
    Create test FastAPI application using app factory.

    Uses DI container for proper dependency injection.
    """
    from src.main import create_test_app
    from src.core.container import get_db

    async def get_test_db():
        yield db_session

    test_app = create_test_app(
        db_session_override=get_test_db,
    )

    yield test_app

    # Cleanup
    test_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """
    Async HTTP client for API testing.
    """
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def authenticated_client(app, test_user, test_token):
    """
    Async HTTP client with authentication headers.
    """
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {test_token}"},
    ) as client:
        yield client
