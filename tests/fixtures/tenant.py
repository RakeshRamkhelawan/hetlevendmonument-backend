"""
tests/fixtures/tenant.py - Multi-Tenant Test Fixtures

Provides fixtures for testing multi-tenant functionality using
the new request-scoped TenantContext pattern.

KEY PRINCIPLES:
1. Unique tenant IDs per test (forward-only pattern)
2. Request-scoped context (no ContextVar issues)
3. Easy to create cross-tenant test scenarios
4. Proper tenant isolation verification

Created: 2025-12-06
"""

import uuid
from typing import Any, AsyncGenerator, Callable, Dict, Optional

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.container import TenantContext


class FixtureData(dict):
    """Dict-like fixture payload that also supports attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


# ============================================================================
# TENANT FACTORY
# ============================================================================


class TenantFactory:
    """Factory for creating test tenants with unique identifiers."""

    def __init__(self, db_session: AsyncSession):
        self._session = db_session

    async def create_tenant(
        self,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a test tenant with unique identifiers.

        Args:
            name: Tenant name (auto-generated if not provided)
            slug: Tenant slug (auto-generated if not provided)
            is_active: Whether tenant is active

        Returns:
            Dict with tenant details including id, name, slug
        """
        from src.core.models.rbac_models import Tenant

        unique_id = uuid.uuid4().hex[:8]
        tenant_name = name or f"Test Tenant {unique_id}"
        tenant_slug = slug or f"test-tenant-{unique_id}"

        tenant = Tenant(
            name=tenant_name,
            slug=tenant_slug,
        )
        self._session.add(tenant)
        await self._session.flush()  # Populate auto-generated ID
        await self._session.commit()
        # No refresh needed: db_session uses expire_on_commit=False

        return FixtureData(
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": is_active,
            }
        )

    async def create_multiple_tenants(self, count: int) -> list:
        """Create multiple tenants for cross-tenant testing."""
        tenants = []
        for i in range(count):
            tenant = await self.create_tenant(name=f"Tenant {i+1}")
            tenants.append(tenant)
        return tenants


@pytest.fixture
def tenant_factory(db_session: AsyncSession) -> TenantFactory:
    """Provide TenantFactory instance."""
    return TenantFactory(db_session)


# ============================================================================
# TENANT FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_tenant(db_session: AsyncSession) -> Dict[str, Any]:
    """
    Create a standard test tenant.

    Each test gets a unique tenant for isolation.
    """
    factory = TenantFactory(db_session)
    return await factory.create_tenant()


@pytest_asyncio.fixture
async def test_tenant_2(db_session: AsyncSession) -> Dict[str, Any]:
    """
    Create a second test tenant for cross-tenant testing.

    Use this when testing tenant isolation:
        def test_isolation(test_tenant, test_tenant_2):
            # Create data in tenant 1
            # Verify tenant 2 cannot access it

    Note: Uses unique name to prevent UNIQUE constraint violations
    when running multiple tests that use cross-tenant setup.
    """
    factory = TenantFactory(db_session)
    # Don't pass hardcoded name - let factory generate unique one
    return await factory.create_tenant()


@pytest_asyncio.fixture
async def inactive_tenant(db_session: AsyncSession) -> Dict[str, Any]:
    """Create an inactive tenant for testing access restrictions."""
    factory = TenantFactory(db_session)
    return await factory.create_tenant(is_active=False)


# ============================================================================
# POSTGRESQL TENANT FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def postgres_test_tenant(postgres_session: AsyncSession) -> Dict[str, Any]:
    """
    Create a test tenant in PostgreSQL database.

    For production-like testing with real PostgreSQL.
    """
    factory = TenantFactory(postgres_session)
    return await factory.create_tenant()


@pytest_asyncio.fixture
async def isolated_tenant(db_session: AsyncSession) -> Dict[str, Any]:
    """
    Create an isolated test tenant (alias for backward compatibility).

    Returns tenant dictionary with 'tenant_id' key for backward compatibility
    with older agentic tests that expect this naming convention.
    Also creates a test user and includes 'user_id' for session tests.
    """
    from src.core.models.rbac_models import User

    factory = TenantFactory(db_session)
    tenant = await factory.create_tenant()

    # Create a test user for this tenant
    user = User(
        email=f"isolated-{tenant['slug']}@example.com",
        hashed_password="$2b$12$9uHPFyLPJcBD/WCRNXgueetgH6HI69HW3AWR1RtIKfwM7qE1v3B6C",
        tenant_id=tenant["id"],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    # No refresh needed: db_session uses expire_on_commit=False

    # Add tenant_id and user_id aliases for backward compatibility.
    # Also add a JWT token so generated tests that access isolated_tenant['token']
    # can authenticate without KeyError.
    from src.core.api.dependencies import create_access_token

    token = create_access_token(
        data={
            "sub": str(user.id),
            "tenant_id": tenant["id"],
            "roles": [],
        }
    )
    tenant["tenant_id"] = tenant["id"]
    tenant["user_id"] = user.id
    tenant["token"] = token
    return tenant


# ============================================================================
# TENANT CONTEXT FIXTURES
# ============================================================================


@pytest.fixture
def tenant_context(test_tenant: Dict[str, Any]) -> TenantContext:
    """
    Create TenantContext for test_tenant.

    Usage:
        def test_endpoint(tenant_context):
            # tenant_context.tenant_id is set to test_tenant's ID
    """
    return TenantContext(
        tenant_id=test_tenant["id"],
        tenant_slug=test_tenant["slug"],
        bypass_filter=False,
    )


@pytest.fixture
def tenant_context_2(test_tenant_2: Dict[str, Any]) -> TenantContext:
    """Create TenantContext for second tenant."""
    return TenantContext(
        tenant_id=test_tenant_2["id"],
        tenant_slug=test_tenant_2["slug"],
        bypass_filter=False,
    )


@pytest.fixture
def bypass_tenant_context(test_tenant: Dict[str, Any]) -> TenantContext:
    """
    Create TenantContext with bypass_filter=True.

    Use for testing admin operations that need to access all tenants.
    """
    return TenantContext(
        tenant_id=test_tenant["id"],
        bypass_filter=True,
    )


@pytest.fixture
def no_tenant_context() -> TenantContext:
    """
    Create empty TenantContext (no tenant set).

    Use for testing public endpoints or unauthenticated access.
    """
    return TenantContext(tenant_id=None, bypass_filter=False)


# ============================================================================
# TENANT CONTEXT OVERRIDES
# ============================================================================


@pytest.fixture
def tenant_context_override(tenant_context: TenantContext) -> Callable:
    """
    Create FastAPI dependency override for TenantContext.

    Usage:
        def test_endpoint(app, tenant_context_override):
            from src.core.container import get_tenant_context
            app.dependency_overrides[get_tenant_context] = tenant_context_override
    """

    def override():
        return tenant_context

    return override


@pytest.fixture
def tenant_context_2_override(tenant_context_2: TenantContext) -> Callable:
    """Create override for second tenant context."""

    def override():
        return tenant_context_2

    return override


@pytest.fixture
def bypass_tenant_override(bypass_tenant_context: TenantContext) -> Callable:
    """Create override with bypass enabled."""

    def override():
        return bypass_tenant_context

    return override


@pytest.fixture
def no_tenant_override(no_tenant_context: TenantContext) -> Callable:
    """Create override with no tenant (public access)."""

    def override():
        return no_tenant_context

    return override


# ============================================================================
# ROLE FIXTURES (Tenant-scoped)
# ============================================================================


@pytest_asyncio.fixture
async def test_role(db_session: AsyncSession, test_tenant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standard test role within test_tenant.
    """
    from src.core.models.rbac_models import Role

    role = Role(
        name="test_role",
        tenant_id=test_tenant["id"],
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.commit()
    # No refresh needed: db_session uses expire_on_commit=False

    return {
        "id": role.id,
        "name": role.name,
        "tenant_id": test_tenant["id"],
    }


@pytest_asyncio.fixture
async def admin_role(db_session: AsyncSession, test_tenant: Dict[str, Any]) -> Dict[str, Any]:
    """Create an admin role within test_tenant."""
    from src.core.models.rbac_models import Role

    role = Role(
        name="admin",
        tenant_id=test_tenant["id"],
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.commit()
    # No refresh needed: db_session uses expire_on_commit=False

    return {
        "id": role.id,
        "name": role.name,
        "tenant_id": test_tenant["id"],
    }


# ============================================================================
# CROSS-TENANT TEST UTILITIES
# ============================================================================


@pytest_asyncio.fixture
async def cross_tenant_setup(
    db_session: AsyncSession,
    test_tenant: Dict[str, Any],
    test_tenant_2: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Set up complete cross-tenant test environment.

    Creates two tenants with users and roles for isolation testing.

    Returns:
        Dict with tenant1, tenant2, user1, user2, etc.
    """
    from src.core.models.rbac_models import Role, User

    # Create users in each tenant
    user1 = User(
        email=f"user-{uuid.uuid4().hex[:8]}@tenant1.com",
        hashed_password="test_hash",
        tenant_id=test_tenant["id"],
    )
    user2 = User(
        email=f"user-{uuid.uuid4().hex[:8]}@tenant2.com",
        hashed_password="test_hash",
        tenant_id=test_tenant_2["id"],
    )

    db_session.add_all([user1, user2])
    await db_session.flush()
    await db_session.commit()
    # No refresh needed: db_session uses expire_on_commit=False

    return {
        "tenant1": test_tenant,
        "tenant2": test_tenant_2,
        "user1": {"id": user1.id, "email": user1.email, "tenant_id": test_tenant["id"]},
        "user2": {
            "id": user2.id,
            "email": user2.email,
            "tenant_id": test_tenant_2["id"],
        },
        "context1": TenantContext(tenant_id=test_tenant["id"]),
        "context2": TenantContext(tenant_id=test_tenant_2["id"]),
    }


# ============================================================================
# LEGACY COMPATIBILITY (ContextVar pattern)
# ============================================================================


@pytest.fixture
def legacy_tenant_context(test_tenant: Dict[str, Any]):
    """
    DEPRECATED: Set tenant context using old ContextVar pattern.

    This is kept for backward compatibility during migration.
    New tests should use tenant_context_override instead.
    """
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

    set_tenant_id(test_tenant["id"])

    yield test_tenant

    clear_tenant_context()


@pytest.fixture
def legacy_bypass_tenant_filter():
    """
    DEPRECATED: Set bypass flag using old ContextVar pattern.
    """
    try:
        from src.core.database.tenant_query_filter import set_bypass_tenant_filter

        set_bypass_tenant_filter(True)
        yield
        set_bypass_tenant_filter(False)
    except ImportError:
        yield  # Module not available
