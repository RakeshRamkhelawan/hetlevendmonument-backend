"""Foundation Portal integration test fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.governance.rate_limiter import reset_snapshot_rate_limits
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    FoundationPortalSettings,
    PortalRole,
    PortalUser,
    Privacy,
)


# ============================================================================
# Rate-limit isolation — reset between tests so one test's quota does not
# exhaust the next test's budget (especially magic-link 5/min IP limit).
# ============================================================================


@pytest.fixture(autouse=True)
async def _clear_rate_limits() -> AsyncGenerator[None, None]:
    """Reset all rate limiter state before and after every foundation test.

    ``reset_snapshot_rate_limits()`` only clears the InMemory fallback limiter.
    These tests run against a REAL Redis backend (``RedisRateLimiter.check_limit``
    does an INCR Lua script directly on Redis), so that reset alone is a no-op
    for them and was, for the whole life of this fixture, silently not doing
    what its docstring said.

    Found 2026-09-03 (PR #163): after fixing a cross-endpoint Redis-key collision
    in rate_limiter.py (require_portal_auth_rate_limit / _takedown_ / _newsletter_
    all shared one bare ``ip:<host>`` bucket), the fix correctly started enforcing
    per-endpoint limits -- which then exposed that NO foundation test file resets
    the real Redis state between tests. Symptom measured in CI: 13 tests across
    test_auth.py and test_newsletter.py failing with ``assert 429 == <expected>``,
    each on its own first, otherwise-legitimate request -- inheriting an exhausted
    bucket from whichever test happened to run first in the same 60s/3600s window.
    Reset BEFORE each test (not just after) so the first test in a session is not
    exposed to leftover state from something that ran earlier in the same process.
    """
    try:
        from src.core.database.redis import get_redis_client

        client = await get_redis_client()
        keys = await client.keys("portal_*:*")
        keys += await client.keys("ip:*")
        keys += await client.keys("email:*")
        if keys:
            await client.delete(*keys)
    except Exception:
        # Geen Redis beschikbaar (unit-achtige run zonder integratie-infra) -- de
        # InMemory-fallback is dan actief en reset_snapshot_rate_limits() volstaat.
        pass
    yield
    reset_snapshot_rate_limits()


# ============================================================================
# Portal JWT helper
# ============================================================================


def _build_portal_token(
    *, user_id: int, email: str, tenant_id: int, role: PortalRole = PortalRole.VISITOR
) -> str:
    """Create a portal JWT (aud='portal', scope='portal_uploader') for foundation endpoint tests."""
    data: dict[str, object] = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "aud": "portal",
        "scope": "portal_uploader",
        "role": role.value,
    }
    return jwt_handler.create_access_token(data=data)


# ============================================================================
# Portal user fixtures (seeded via ORM for FK integrity)
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def portal_visitor_user(postgres_session: AsyncSession) -> PortalUser:
    """Seed a portal visitor user for tenant_id=1."""
    user = PortalUser(
        tenant_id=1,
        email="visitor@test.local",
        display_name="Test Visitor",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.VISITOR,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def portal_curator_user(postgres_session: AsyncSession) -> PortalUser:
    """Seed a portal curator user for tenant_id=1."""
    user = PortalUser(
        tenant_id=1,
        email="curator@test.local",
        display_name="Test Curator",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.CURATOR,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def portal_admin_user(postgres_session: AsyncSession) -> PortalUser:
    """Seed a portal admin user for tenant_id=1."""
    user = PortalUser(
        tenant_id=1,
        email="portaladmin@test.local",
        display_name="Test Portal Admin",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.ADMIN,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def other_tenant_portal_user(postgres_session: AsyncSession) -> PortalUser:
    """Seed a portal user belonging to tenant_id=2 (for cross-tenant tests)."""
    user = PortalUser(
        tenant_id=2,
        email="other@test.local",
        display_name="Other Tenant User",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.VISITOR,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return user


# ============================================================================
# Portal token fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def portal_visitor_token(portal_visitor_user: PortalUser) -> str:
    """JWT token for the visitor portal user."""
    return _build_portal_token(
        user_id=portal_visitor_user.id,
        email=portal_visitor_user.email,
        tenant_id=portal_visitor_user.tenant_id,
        role=PortalRole.VISITOR,
    )


@pytest_asyncio.fixture(scope="function")
async def portal_curator_token(portal_curator_user: PortalUser) -> str:
    """JWT token for the curator portal user."""
    return _build_portal_token(
        user_id=portal_curator_user.id,
        email=portal_curator_user.email,
        tenant_id=portal_curator_user.tenant_id,
        role=PortalRole.CURATOR,
    )


@pytest_asyncio.fixture(scope="function")
async def portal_admin_token(portal_admin_user: PortalUser) -> str:
    """JWT token for the portal admin user."""
    return _build_portal_token(
        user_id=portal_admin_user.id,
        email=portal_admin_user.email,
        tenant_id=portal_admin_user.tenant_id,
        role=PortalRole.ADMIN,
    )


@pytest_asyncio.fixture(scope="function")
async def other_tenant_portal_token(other_tenant_portal_user: PortalUser) -> str:
    """JWT token for the other-tenant portal user."""
    return _build_portal_token(
        user_id=other_tenant_portal_user.id,
        email=other_tenant_portal_user.email,
        tenant_id=other_tenant_portal_user.tenant_id,
        role=PortalRole.VISITOR,
    )


# ============================================================================
# Seeded content fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def approved_public_content(postgres_session: AsyncSession) -> FoundationContent:
    """Seed an approved public content item for tenant_id=1."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.STORY,
        title_nl="Test Verhaal",
        title_en="Test Story",
        description_nl="Een test beschrijving",
        privacy=Privacy.PUBLIC,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
        category="herinnering",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def approved_community_content(postgres_session: AsyncSession) -> FoundationContent:
    """Seed an approved community content item for tenant_id=1."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.ARTWORK,
        title_nl="Test Kunstwerk",
        title_en="Test Artwork",
        privacy=Privacy.COMMUNITY,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
        category="kunst",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def pending_content(postgres_session: AsyncSession) -> FoundationContent:
    """Seed a pending content item for tenant_id=1."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.POETRY,
        title_nl="Test Gedicht",
        privacy=Privacy.PUBLIC,
        status=ContentStatus.PENDING,
        rights_confirmed=True,
        category="poëzie",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def other_tenant_content(postgres_session: AsyncSession) -> FoundationContent:
    """Seed an approved content item for tenant_id=2 (cross-tenant test)."""
    content = FoundationContent(
        tenant_id=2,
        type=ContentType.STORY,
        title_nl="Ander Verhaal",
        privacy=Privacy.PUBLIC,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


# ============================================================================
# Portal settings fixture
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def portal_settings(postgres_session: AsyncSession) -> FoundationPortalSettings:
    """Seed portal settings for tenant_id=1."""
    settings = FoundationPortalSettings(
        tenant_id=1,
        platform_name_nl="Ketikoti Vlaardingen",
        platform_name_en="Ketikoti Vlaardingen",
        primary_color="#1a2f45",
        accent_color="#e8b86d",
        contact_email="info@ketikotivlaardingen.nl",
    )
    postgres_session.add(settings)
    await postgres_session.flush()
    await postgres_session.refresh(settings)
    return settings
