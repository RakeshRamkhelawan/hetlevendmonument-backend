"""Integration test fixtures for scheduling module.

Uses real PostgreSQL database (no mocks) for true integration testing.
Requires test database running on localhost:5435.

SKIPPED: These tests hang on Python 3.13 + pytest-asyncio due to
event loop deadlock in session-scoped fixtures. Re-enable when
pytest-asyncio 0.24+ is available with ProactorEventLoop fix.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Hangs on Python 3.13: pytest-asyncio ProactorEventLoop deadlock. "
    "Fix: upgrade pytest-asyncio >= 0.24 or run with --asyncio-mode=strict"
)

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db

# Test user constants
TEST_TENANT_ID = 999
TEST_USER_ID = 9999
TEST_USER_EMAIL = "test@scheduling.integration"


def create_scheduling_app(
    db_session_override,
    user_override,
) -> FastAPI:
    """Create a minimal FastAPI app with only scheduling routes."""
    from fastapi import FastAPI
    from slowapi.errors import RateLimitExceeded

    from src.core.api.setup.exception_handlers import setup_exception_handlers
    from src.core.middleware.rate_limiter import get_limiter, rate_limit_exceeded_handler

    app = FastAPI(title="Scheduling Integration Test")

    # Setup rate limiter
    limiter = get_limiter("scheduling")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    setup_exception_handlers(app)

    # Override dependencies
    app.dependency_overrides[get_db] = db_session_override
    app.dependency_overrides[get_current_user] = user_override

    # Import and include scheduling routers
    from src.core.scheduling.api.conflict_routes import router as conflict_router
    from src.core.scheduling.api.integration_routes import router as integ_router
    from src.core.scheduling.api.mobile_routes import router as mobile_router
    from src.core.scheduling.api.partner_routes import router as partner_router
    from src.core.scheduling.api.routes import router as scheduling_router
    from src.core.scheduling.api.smart_routes import router as smart_router
    from src.core.scheduling.api.voice_routes import router as voice_router
    from src.core.scheduling.api.webhook_routes import router as webhook_router

    app.include_router(scheduling_router, prefix="/api/v1", tags=["Scheduling"])
    app.include_router(integ_router, prefix="/api/v1", tags=["Integrations"])
    app.include_router(smart_router, prefix="/api/v1", tags=["Smart Scheduling"])
    app.include_router(webhook_router, prefix="/api/v1/scheduling", tags=["Webhooks"])
    app.include_router(conflict_router, prefix="/api/v1", tags=["Conflicts"])
    app.include_router(partner_router, prefix="/api/v1", tags=["Partners"])
    app.include_router(mobile_router, prefix="/api/v1", tags=["Mobile"])
    app.include_router(voice_router, prefix="/api/v1", tags=["Voice"])

    return app


@pytest_asyncio.fixture(scope="function")
async def test_user(postgres_session: AsyncSession) -> UserResponse:
    """Create a test user in the database."""
    from src.core.models.rbac_models import Tenant, User

    # Create tenant
    tenant = Tenant(
        id=TEST_TENANT_ID,
        name="Scheduling Test Tenant",
        domain="scheduling.test",
        created_at=datetime.now(timezone.utc),
    )
    postgres_session.add(tenant)

    # Create user (without roles to avoid async issues)
    user = User(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        tenant_id=TEST_TENANT_ID,
        hashed_password="$2b$12$fakehashfortesting",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    postgres_session.add(user)
    await postgres_session.flush()

    return UserResponse(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        tenant_id=TEST_TENANT_ID,
        roles=["admin"],
    )


@pytest_asyncio.fixture(scope="function")
async def async_client(
    postgres_session: AsyncSession,
    test_user: UserResponse,
) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client with real database and test user."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Override DB dependency to use test session."""
        yield postgres_session

    async def override_get_current_user() -> UserResponse:
        """Override auth to use test user."""
        return test_user

    # Create app with scheduling routers only
    app = create_scheduling_app(override_get_db, override_get_current_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def partner_factory(postgres_session: AsyncSession):
    """Factory for creating design partners in tests."""
    from src.core.scheduling.partners.models import DesignPartner

    async def create_partner(
        name: str = "Test Partner",
        industry: str = "Technology",
        status: str = "active",
        contact_email: str = "partner@test.com",
        **kwargs,
    ) -> DesignPartner:
        partner = DesignPartner(
            tenant_id=TEST_TENANT_ID,
            name=name,
            industry=industry,
            contact_email=contact_email,
            status=status,
            start_date=datetime.now(timezone.utc),
            end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
            **kwargs,
        )
        postgres_session.add(partner)
        await postgres_session.flush()
        return partner

    return create_partner


@pytest_asyncio.fixture(scope="function")
async def event_factory(postgres_session: AsyncSession):
    """Factory for creating calendar events in tests."""
    from src.core.scheduling.models import CalendarEvent

    async def create_event(
        title: str = "Test Event",
        start_time: datetime = None,
        end_time: datetime = None,
        **kwargs,
    ) -> CalendarEvent:
        now = datetime.now(timezone.utc)
        event = CalendarEvent(
            tenant_id=TEST_TENANT_ID,
            user_id=str(TEST_USER_ID),
            organizer_id=kwargs.pop("organizer_id", str(TEST_USER_ID)),
            title=title,
            start_time=start_time or now,
            # NOOIT now.replace(hour=now.hour + 1): bij now.hour == 23 geeft dat
            # ValueError: hour must be in 0..23 (raakte CI op 2026-09-09, 20 tests
            # tegelijk, precies om 23:5x UTC). timedelta rolt correct door naar de
            # volgende dag.
            end_time=end_time or now + timedelta(hours=1),
            **kwargs,
        )
        postgres_session.add(event)
        await postgres_session.flush()
        return event

    return create_event


@pytest_asyncio.fixture(scope="function")
async def integration_factory(postgres_session: AsyncSession):
    """Factory for creating calendar integrations in tests."""
    import uuid

    from src.core.scheduling.integrations.models import CalendarIntegration

    # Counter for generating unique user_ids
    _user_counter = 0

    async def create_integration(
        provider: str = "google",
        provider_account_id: str = "test@example.com",
        **kwargs,
    ) -> CalendarIntegration:
        nonlocal _user_counter
        _user_counter += 1

        # Generate unique user_id to avoid unique constraint violation
        # (tenant_id, user_id, provider) must be unique
        unique_user_id = kwargs.pop(
            "user_id", f"{TEST_USER_ID}_{_user_counter}_{uuid.uuid4().hex[:8]}"
        )

        # Build integration data with defaults, allowing kwargs to override
        integration_data = {
            "tenant_id": TEST_TENANT_ID,
            "user_id": str(unique_user_id),
            "provider": provider,
            "provider_account_id": provider_account_id,
            "access_token_encrypted": "fake_access_token_encrypted",
            "refresh_token_encrypted": "fake_refresh_token_encrypted",
            "is_active": True,
        }
        integration_data.update(kwargs)

        integration = CalendarIntegration(**integration_data)
        postgres_session.add(integration)
        await postgres_session.flush()
        return integration

    return create_integration


@pytest_asyncio.fixture(scope="function")
async def conflict_factory(postgres_session: AsyncSession, integration_factory, event_factory):
    """Factory for creating sync conflicts in tests."""
    from src.core.scheduling.webhooks.models import SyncConflict

    async def create_conflict(
        conflict_type: str = "duplicate", severity: str = "medium", **kwargs
    ) -> SyncConflict:
        # Create integration first if not provided
        integration_id = kwargs.get("integration_id")
        if not integration_id:
            integration = await integration_factory()
            integration_id = integration.id

        # Create a real calendar event if local_event_id not provided
        local_event_id = kwargs.get("local_event_id")
        if not local_event_id:
            event = await event_factory()
            local_event_id = event.id

        # Set defaults for required fields if not in kwargs
        # Note: external_snapshot needs start_time and end_time for _reconstruct_external_event
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        conflict_data = {
            "tenant_id": TEST_TENANT_ID,
            "integration_id": integration_id,
            "conflict_type": conflict_type,
            "severity": severity,
            "local_event_id": local_event_id,
            "external_event_id": "ext-123",
            "local_snapshot": {"title": "Local Event"},
            "external_snapshot": {
                "title": "External Event",
                "start_time": now.isoformat(),
                "end_time": now.isoformat(),
            },
            "resolution_status": "pending",
        }
        conflict_data.update(kwargs)

        conflict = SyncConflict(**conflict_data)
        postgres_session.add(conflict)
        await postgres_session.flush()
        return conflict

    return create_conflict
