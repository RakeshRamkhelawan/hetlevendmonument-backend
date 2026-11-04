"""
Agency Integration Test Fixtures

Provides fixtures specifically for Agency capabilities integration tests.
These fixtures create real database records and real authentication tokens.

NO MOCKDATA - All fixtures create real records in test database.
"""

import uuid
from typing import Any, AsyncGenerator, Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ============================================================================
# TENANT FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def tenant_a(db_session: AsyncSession) -> Dict[str, Any]:
    """Create tenant A for isolation testing."""
    from src.core.models.rbac_models import Tenant

    tenant = Tenant(
        name="Tenant A",
        slug=f"tenant-a-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
    }


@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession) -> Dict[str, Any]:
    """Create tenant B for isolation testing."""
    from src.core.models.rbac_models import Tenant

    tenant = Tenant(
        name="Tenant B",
        slug=f"tenant-b-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
    }


# ============================================================================
# USER FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def admin_user_tenant_a(
    db_session: AsyncSession,
    tenant_a: Dict[str, Any],
) -> Dict[str, Any]:
    """Create admin user in tenant A with real JWT token."""
    from src.core.auth.jwt import create_access_token
    from src.core.models.rbac_models import Role, RolePermission, User

    # Create admin role for tenant A
    admin_role = Role(
        tenant_id=tenant_a["id"],
        name="admin",
        description="Admin role",
        is_active=True,
    )
    db_session.add(admin_role)
    await db_session.flush()

    # Add wildcard permissions
    perm = RolePermission(
        role_id=admin_role.id,
        tenant_id=tenant_a["id"],
        resource="*",
        action="*",
    )
    db_session.add(perm)

    # Create user with known password hash (password: "testpass123")
    user = User(
        email=f"admin-a-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="$2b$12$9uHPFyLPJcBD/WCRNXgueetgH6HI69HW3AWR1RtIKfwM7qE1v3B6C",
        tenant_id=tenant_a["id"],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Link user to role
    from src.core.models.rbac_models import user_roles

    await db_session.execute(
        user_roles.insert().values(
            user_id=user.id,
            role_id=admin_role.id,
            tenant_id=tenant_a["id"],
        )
    )

    await db_session.commit()
    await db_session.refresh(user)

    # Create real JWT token
    token = create_access_token(
        data={
            "sub": str(user.id),
            "tenant_id": tenant_a["id"],
            "roles": ["admin"],
        }
    )

    return {
        "id": user.id,
        "email": user.email,
        "tenant_id": tenant_a["id"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def admin_user_tenant_b(
    db_session: AsyncSession,
    tenant_b: Dict[str, Any],
) -> Dict[str, Any]:
    """Create admin user in tenant B with real JWT token."""
    from src.core.auth.jwt import create_access_token
    from src.core.models.rbac_models import Role, RolePermission, User

    # Create admin role for tenant B
    admin_role = Role(
        tenant_id=tenant_b["id"],
        name="admin",
        description="Admin role",
        is_active=True,
    )
    db_session.add(admin_role)
    await db_session.flush()

    # Add wildcard permissions
    perm = RolePermission(
        role_id=admin_role.id,
        tenant_id=tenant_b["id"],
        resource="*",
        action="*",
    )
    db_session.add(perm)

    # Create user
    user = User(
        email=f"admin-b-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="$2b$12$9uHPFyLPJcBD/WCRNXgueetgH6HI69HW3AWR1RtIKfwM7qE1v3B6C",
        tenant_id=tenant_b["id"],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Link user to role
    from src.core.models.rbac_models import user_roles

    await db_session.execute(
        user_roles.insert().values(
            user_id=user.id,
            role_id=admin_role.id,
            tenant_id=tenant_b["id"],
        )
    )

    await db_session.commit()
    await db_session.refresh(user)

    # Create real JWT token
    token = create_access_token(
        data={
            "sub": str(user.id),
            "tenant_id": tenant_b["id"],
            "roles": ["admin"],
        }
    )

    return {
        "id": user.id,
        "email": user.email,
        "tenant_id": tenant_b["id"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ============================================================================
# TOKEN FIXTURES (for convenience)
# ============================================================================


@pytest.fixture
def admin_token_tenant_a(admin_user_tenant_a: Dict[str, Any]) -> str:
    """Get admin token for tenant A."""
    return admin_user_tenant_a["token"]


@pytest.fixture
def admin_token_tenant_b(admin_user_tenant_b: Dict[str, Any]) -> str:
    """Get admin token for tenant B."""
    return admin_user_tenant_b["token"]


# ============================================================================
# AGENT FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_agent_tenant_a(
    db_session: AsyncSession,
    tenant_a: Dict[str, Any],
    admin_user_tenant_a: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a real agent in tenant A via the AgentRegistry.
    """
    from src.core.agents.agent_registry import AgentRegistry

    agent_id = f"test-agent-a-{uuid.uuid4().hex[:8]}"

    agent = await AgentRegistry.create_agent(
        agent_type="planner",
        tenant_id=tenant_a["id"],
        name="Test Agent A",
        created_by=admin_user_tenant_a["id"],
    )

    return {
        "id": agent.agent_id,
        "type": agent.agent_type,
        "tenant_id": tenant_a["id"],
        "name": agent.name,
    }


@pytest_asyncio.fixture
async def test_agent_tenant_b(
    db_session: AsyncSession,
    tenant_b: Dict[str, Any],
    admin_user_tenant_b: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a real agent in tenant B via the AgentRegistry.
    """
    from src.core.agents.agent_registry import AgentRegistry

    agent_id = f"test-agent-b-{uuid.uuid4().hex[:8]}"

    agent = await AgentRegistry.create_agent(
        agent_type="planner",
        tenant_id=tenant_b["id"],
        name="Test Agent B",
        created_by=admin_user_tenant_b["id"],
    )

    return {
        "id": agent.agent_id,
        "type": agent.agent_type,
        "tenant_id": tenant_b["id"],
        "name": agent.name,
    }


# ============================================================================
# AUTHENTICATED CLIENT FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def async_client_tenant_a(
    admin_user_tenant_a: Dict[str, Any],
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Async client authenticated as tenant A admin.
    """
    from src.core.auth.dependencies import get_current_user_id
    from src.core.database.database import get_async_session
    from src.main import app

    # Override dependencies
    async def override_get_user_id():
        return admin_user_tenant_a["id"]

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_get_user_id
    app.dependency_overrides[get_async_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=admin_user_tenant_a["headers"],
    ) as client:
        yield client

    # Cleanup overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client_tenant_b(
    admin_user_tenant_b: Dict[str, Any],
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Async client authenticated as tenant B admin.
    """
    from src.core.auth.dependencies import get_current_user_id
    from src.core.database.database import get_async_session
    from src.main import app

    # Override dependencies
    async def override_get_user_id():
        return admin_user_tenant_b["id"]

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_current_user_id] = override_get_user_id
    app.dependency_overrides[get_async_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=admin_user_tenant_b["headers"],
    ) as client:
        yield client

    # Cleanup overrides
    app.dependency_overrides.clear()


# ============================================================================
# COMPATIBILITY ALIASES (for test readability)
# ============================================================================


@pytest.fixture
def test_tenant(tenant_a: Dict[str, Any]) -> Dict[str, Any]:
    """Alias for tenant_a."""
    return tenant_a


@pytest.fixture
def admin_token(admin_token_tenant_a: str) -> str:
    """Alias for tenant A admin token."""
    return admin_token_tenant_a


@pytest.fixture
def test_agent(test_agent_tenant_a: Dict[str, Any]) -> Dict[str, Any]:
    """Alias for tenant A test agent."""
    return test_agent_tenant_a


@pytest.fixture
def admin_token_tenant_a_alias(admin_token_tenant_a: str) -> str:
    """Alias for tenant A token."""
    return admin_token_tenant_a


@pytest.fixture
def admin_token_tenant_b_alias(admin_token_tenant_b: str) -> str:
    """Alias for tenant B token."""
    return admin_token_tenant_b
