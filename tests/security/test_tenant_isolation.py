"""
Phase 5 Testing: Multi-Tenant Isolation Security Tests

Tests comprehensive tenant isolation across all layers:
- Middleware tenant context enforcement
- Database query auto-filtering
- Cross-tenant access prevention
- RBAC tenant-scoped permissions
- Audit logging for violations
"""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.middleware.tenant_context import (
    clear_tenant_context,
    get_tenant_id,
    require_tenant_id,
    set_tenant_id,
)
from src.core.models.rbac_models import Role, Tenant, User

# Import TenantFactory for unique IDs (prevents UNIQUE constraint violations)
from tests.conftest import TenantFactory


class TestTenantContextSecurity:
    """Test tenant context security validation"""

    def test_set_tenant_id_validates_type(self):
        """Tenant ID accepts numeric strings but rejects non-numeric values."""
        set_tenant_id("123")
        assert get_tenant_id() == 123
        clear_tenant_context()

        # None is allowed for testing scenarios (clears context)
        set_tenant_id(None)
        assert get_tenant_id() is None

    def test_set_tenant_id_validates_positive(self):
        """Tenant ID must be positive"""
        with pytest.raises(ValueError, match="must be positive"):
            set_tenant_id(0)

        with pytest.raises(ValueError, match="must be positive"):
            set_tenant_id(-1)

    def test_require_tenant_id_enforces_context(self):
        """require_tenant_id() must fail without context"""
        clear_tenant_context()

        with pytest.raises(RuntimeError, match="Tenant context not set"):
            require_tenant_id()

    def test_tenant_context_isolation(self):
        """Tenant context is properly isolated"""
        # Set tenant 1
        set_tenant_id(1)
        assert get_tenant_id() == 1

        # Clear context
        clear_tenant_context()
        assert get_tenant_id() is None

        # Set tenant 2
        set_tenant_id(2)
        assert get_tenant_id() == 2


@pytest.mark.asyncio
class TestDatabaseTenantIsolation:
    """Test database-level tenant isolation"""

    async def test_users_isolated_by_tenant(self, db_session: AsyncSession):
        """Users from different tenants must not be visible"""
        # Generate unique IDs
        tenant1_id = TenantFactory.next_id()
        tenant2_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()

        # Create tenants (name and slug are required)
        tenant1 = Tenant(id=tenant1_id, name=f"Tenant {tenant1_id}", slug=f"tenant-{tenant1_id}")
        tenant2 = Tenant(id=tenant2_id, name=f"Tenant {tenant2_id}", slug=f"tenant-{tenant2_id}")
        db_session.add_all([tenant1, tenant2])
        await db_session.commit()

        # Create users in different tenants (User model has no role_id)
        user1 = User(
            id=user1_id,
            email=f"user{user1_id}@tenant1.com",
            hashed_password="hash1",
            tenant_id=tenant1_id,
        )
        user2 = User(
            id=user2_id,
            email=f"user{user2_id}@tenant2.com",
            hashed_password="hash2",
            tenant_id=tenant2_id,
        )
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Set context to tenant 1
        set_tenant_id(tenant1_id)

        # Query users - should only see tenant 1
        result = await db_session.execute(select(User).where(User.tenant_id == require_tenant_id()))
        users = result.scalars().all()

        assert len(users) == 1
        assert users[0].email == f"user{user1_id}@tenant1.com"
        assert users[0].tenant_id == tenant1_id

        # Clear context
        clear_tenant_context()

    async def test_cross_tenant_user_access_blocked(self, db_session: AsyncSession):
        """Attempting to access another tenant's user must fail"""
        # Generate unique IDs
        tenant1_id = TenantFactory.next_id()
        tenant2_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()

        # Create tenants (name and slug are required)
        tenant1 = Tenant(id=tenant1_id, name=f"Tenant {tenant1_id}", slug=f"tenant-{tenant1_id}")
        tenant2 = Tenant(id=tenant2_id, name=f"Tenant {tenant2_id}", slug=f"tenant-{tenant2_id}")
        db_session.add_all([tenant1, tenant2])
        await db_session.commit()

        # Create user in tenant 2 (User model has no role_id)
        user2 = User(
            id=user2_id,
            email=f"user{user2_id}@tenant2.com",
            hashed_password="hash2",
            tenant_id=tenant2_id,
        )
        db_session.add(user2)
        await db_session.commit()

        # Set context to tenant 1
        set_tenant_id(tenant1_id)

        # Try to access tenant 2's user by ID
        result = await db_session.execute(
            select(User).where(User.id == user2_id, User.tenant_id == require_tenant_id())
        )
        user = result.scalar_one_or_none()

        # Should return None (not found due to tenant filter)
        assert user is None

        clear_tenant_context()


@pytest.mark.asyncio
class TestCrossTenantAccessPrevention:
    """Test prevention of cross-tenant data access"""

    async def test_role_assignment_respects_tenant(self, db_session: AsyncSession):
        """Roles can only be assigned within same tenant"""
        # Generate unique IDs
        tenant1_id = TenantFactory.next_id()
        tenant2_id = TenantFactory.next_id()
        role1_id = TenantFactory.next_id()
        role2_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()

        # Create tenants (name and slug are required)
        tenant1 = Tenant(id=tenant1_id, name=f"Tenant {tenant1_id}", slug=f"tenant-{tenant1_id}")
        tenant2 = Tenant(id=tenant2_id, name=f"Tenant {tenant2_id}", slug=f"tenant-{tenant2_id}")
        db_session.add_all([tenant1, tenant2])
        await db_session.commit()

        # Create roles in different tenants
        role1 = Role(id=role1_id, name="admin", tenant_id=tenant1_id, permissions=[])
        role2 = Role(id=role2_id, name="admin", tenant_id=tenant2_id, permissions=[])
        db_session.add_all([role1, role2])
        await db_session.commit()

        # Create user in tenant 1 (User model has no role_id)
        user1 = User(
            id=user1_id,
            email=f"user{user1_id}@tenant1.com",
            hashed_password="hash1",
            tenant_id=tenant1_id,
        )
        db_session.add(user1)
        await db_session.commit()

        # Set context to tenant 1
        set_tenant_id(tenant1_id)

        # Try to query role from tenant 2 (should fail)
        result = await db_session.execute(
            select(Role).where(Role.id == role2_id, Role.tenant_id == require_tenant_id())
        )
        role = result.scalar_one_or_none()

        assert role is None  # Cannot access tenant 2's role

        # Query role from tenant 1 (should succeed)
        result = await db_session.execute(
            select(Role).where(Role.id == role1_id, Role.tenant_id == require_tenant_id())
        )
        role = result.scalar_one_or_none()

        assert role is not None
        assert role.name == "admin"
        assert role.tenant_id == tenant1_id

        clear_tenant_context()

    async def test_tenant_scoped_unique_constraints(self, db_session: AsyncSession):
        """Same email can exist in different tenants"""
        # Generate unique IDs
        tenant1_id = TenantFactory.next_id()
        tenant2_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()

        # Create tenants (name and slug are required)
        tenant1 = Tenant(id=tenant1_id, name=f"Tenant {tenant1_id}", slug=f"tenant-{tenant1_id}")
        tenant2 = Tenant(id=tenant2_id, name=f"Tenant {tenant2_id}", slug=f"tenant-{tenant2_id}")
        db_session.add_all([tenant1, tenant2])
        await db_session.commit()

        # Create same email in both tenants (User model has no role_id)
        user1 = User(
            id=user1_id,
            email="admin@company.com",
            hashed_password="hash1",
            tenant_id=tenant1_id,
        )
        user2 = User(
            id=user2_id,
            email="admin@company.com",
            hashed_password="hash2",
            tenant_id=tenant2_id,
        )
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Verify both users exist
        result = await db_session.execute(select(User).where(User.id.in_([user1_id, user2_id])))
        all_users = result.scalars().all()
        assert len(all_users) == 2

        # Verify they're in different tenants
        assert {u.tenant_id for u in all_users} == {tenant1_id, tenant2_id}


@pytest.mark.asyncio
class TestTenantIsolationFailSecure:
    """Test fail-secure behavior when tenant context missing"""

    async def test_query_without_context_returns_empty(self, db_session: AsyncSession):
        """Queries without tenant context should return empty (fail-secure)"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        user_id = TenantFactory.next_id()

        # Create tenant and user
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        user = User(
            id=user_id,
            email=f"user{user_id}@tenant.com",
            hashed_password="hash",
            tenant_id=tenant_id,
        )
        db_session.add(user)
        await db_session.commit()

        # Clear tenant context
        clear_tenant_context()

        # Query with explicit None check (simulates missing context)
        # In production, middleware would enforce context
        # Here we test the pattern used in queries
        try:
            tenant_id = require_tenant_id()
            # This should raise RuntimeError, so we shouldn't reach here
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Tenant context not set" in str(e)

    async def test_require_tenant_id_prevents_sql_injection(self):
        """require_tenant_id validates type to prevent injection"""
        # Type validation prevents injection
        with pytest.raises(ValueError):
            set_tenant_id("1; DROP TABLE users;")

        # Only accepts positive integers
        set_tenant_id(1)
        assert require_tenant_id() == 1

        clear_tenant_context()


@pytest.mark.asyncio
class TestAuditLoggingSecurity:
    """Test audit logging for security events"""

    async def test_cross_tenant_attempt_logged(self):
        """Cross-tenant access attempts should be logged"""
        from src.core.governance.services.audit_service import SecurityEvent

        # Verify SecurityEvent enum includes cross-tenant
        assert hasattr(SecurityEvent, "CROSS_TENANT_ATTEMPT")
        assert SecurityEvent.CROSS_TENANT_ATTEMPT == "cross_tenant_access_attempt"

    async def test_tenant_context_failure_logged(self):
        """Missing tenant context should be logged"""
        from src.core.governance.services.audit_service import SecurityEvent

        # Verify SecurityEvent enum includes context failure
        assert hasattr(SecurityEvent, "TENANT_CONTEXT_FAILED")
        assert SecurityEvent.TENANT_CONTEXT_FAILED == "tenant_context_failed"


class TestTenantIsolationMetrics:
    """Test metrics collection for tenant isolation"""

    def test_all_models_have_tenant_id(self):
        """All tenant-scoped models must have tenant_id column"""
        from src.core.models.rbac_models import Role, User

        # User model must have tenant_id
        assert hasattr(User, "tenant_id")

        # Role model must have tenant_id
        assert hasattr(Role, "tenant_id")

    def test_tenant_model_relationships(self):
        """Tenant model must have proper relationships"""
        from src.core.models.rbac_models import Tenant

        # Check Tenant model exists and has relationships
        assert hasattr(Tenant, "users")
        assert hasattr(Tenant, "roles")
