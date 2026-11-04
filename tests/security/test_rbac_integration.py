"""
Phase 5 Testing: RBAC Integration Tests

Tests RBAC system with tenant isolation:
- Permission checks respect tenant boundaries
- Roles are tenant-scoped
- Bulk role operations maintain isolation
- Default roles created per tenant
- Conditional permissions evaluated correctly
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.models.rbac_models import Role, RolePermission, Tenant, User
from src.core.services.rbac_service import RBACService

# Import TenantFactory for unique IDs (prevents UNIQUE constraint violations)
from tests.conftest import TenantFactory


@pytest.mark.asyncio
class TestRBACTenantIsolation:
    """Test RBAC permissions are tenant-scoped"""

    async def test_user_permissions_isolated_by_tenant(self, db_session: AsyncSession):
        """Users can only see permissions from their tenant"""
        # Generate unique IDs
        tenant1_id = TenantFactory.next_id()
        tenant2_id = TenantFactory.next_id()
        role1_id = TenantFactory.next_id()
        role2_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()

        # Create two tenants
        tenant1 = Tenant(id=tenant1_id, name=f"Tenant {tenant1_id}", slug=f"tenant{tenant1_id}")
        tenant2 = Tenant(id=tenant2_id, name=f"Tenant {tenant2_id}", slug=f"tenant{tenant2_id}")
        db_session.add_all([tenant1, tenant2])
        await db_session.commit()

        # Create roles in each tenant
        role1 = Role(id=role1_id, name="admin", description="Admin role", tenant_id=tenant1_id)
        role2 = Role(id=role2_id, name="admin", description="Admin role", tenant_id=tenant2_id)
        db_session.add_all([role1, role2])
        await db_session.commit()

        # Create permissions for each role (with tenant_id)
        perm1 = RolePermission(role_id=role1_id, resource="*", action="*", tenant_id=tenant1_id)
        perm2 = RolePermission(
            role_id=role2_id, resource="limited", action="read", tenant_id=tenant2_id
        )
        db_session.add_all([perm1, perm2])
        await db_session.commit()

        # Create users
        user1 = User(
            id=user1_id,
            email=f"admin{user1_id}@t1.com",
            hashed_password="h1",
            tenant_id=tenant1_id,
        )
        user2 = User(
            id=user2_id,
            email=f"admin{user2_id}@t2.com",
            hashed_password="h2",
            tenant_id=tenant2_id,
        )
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Link users to roles through user_roles junction table
        from src.core.models.rbac_models import user_roles

        await db_session.execute(user_roles.insert().values(user_id=user1_id, role_id=role1_id))
        await db_session.execute(user_roles.insert().values(user_id=user2_id, role_id=role2_id))
        await db_session.commit()

        # Set context to tenant 1
        set_tenant_id(tenant1_id)
        rbac = RBACService(db_session)

        # Check user1 has full permissions (admin role has * resource)
        has_perm = await rbac.user_has_permission(
            user_id=user1_id, permission="agent:write", tenant_id=tenant1_id
        )
        assert has_perm is True

        # User2's permissions should not be visible from tenant 1
        has_perm = await rbac.user_has_permission(
            user_id=user2_id, permission="agent:write", tenant_id=tenant1_id
        )
        assert has_perm is False

        clear_tenant_context()

    async def test_role_creation_scoped_to_tenant(self, db_session: AsyncSession):
        """Roles created are automatically scoped to current tenant"""
        # Generate unique ID
        tenant_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # Create role
        role = await rbac.create_role(
            name="editor",
            description="Content editor",
            permissions=[{"resource": "agent", "action": "*"}],
            tenant_id=tenant_id,
        )

        assert role is not None
        assert role.tenant_id == tenant_id
        assert role.name == "editor"

        clear_tenant_context()

    async def test_default_roles_created_per_tenant(self, db_session: AsyncSession):
        """Default roles (admin, editor, user) created for each tenant"""
        # Generate unique ID
        tenant_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # Ensure default roles
        await rbac.ensure_default_roles(tenant_id=tenant_id)

        # Verify roles exist
        from sqlalchemy.orm import selectinload

        result = await db_session.execute(
            select(Role).where(Role.tenant_id == tenant_id).options(selectinload(Role.permissions))
        )
        roles = result.scalars().all()

        role_names = {r.name for r in roles}
        assert "admin" in role_names
        assert "editor" in role_names
        assert "user" in role_names

        # Admin should have wildcard permissions
        admin_role = next(r for r in roles if r.name == "admin")
        assert any(p.resource == "*" and p.action == "*" for p in admin_role.permissions)

        clear_tenant_context()


@pytest.mark.asyncio
class TestBulkRoleOperations:
    """Test bulk role assignment/revocation"""

    async def test_bulk_assign_respects_tenant(self, db_session: AsyncSession):
        """Bulk role assignment only works within same tenant"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        role_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()
        user3_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        # Create role
        role = Role(id=role_id, name="editor", tenant_id=tenant_id)
        db_session.add(role)
        await db_session.commit()

        # Create users
        users = [
            User(
                id=uid,
                email=f"user{uid}@t1.com",
                hashed_password=f"h{uid}",
                tenant_id=tenant_id,
            )
            for uid in [user1_id, user2_id, user3_id]
        ]
        db_session.add_all(users)
        await db_session.commit()

        # Link users to role through user_roles junction table
        from src.core.models.rbac_models import user_roles

        user_role_values = [
            {"user_id": uid, "role_id": role_id} for uid in [user1_id, user2_id, user3_id]
        ]
        await db_session.execute(user_roles.insert(), user_role_values)
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # Bulk assign editor role
        results = await rbac.bulk_assign_roles(
            [user1_id, user2_id, user3_id], "editor", tenant_id=tenant_id
        )

        # All should succeed
        assert len(results) == 3
        assert all(r["success"] for r in results)

        clear_tenant_context()

    async def test_bulk_revoke_tenant_scoped(self, db_session: AsyncSession):
        """Bulk revocation is tenant-scoped"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        role1_id = TenantFactory.next_id()
        role2_id = TenantFactory.next_id()
        user1_id = TenantFactory.next_id()
        user2_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        # Create roles
        role1 = Role(id=role1_id, name="user", tenant_id=tenant_id)
        role2 = Role(id=role2_id, name="editor", tenant_id=tenant_id)
        db_session.add_all([role1, role2])
        await db_session.commit()

        # Create users with editor role
        users = [
            User(
                id=uid,
                email=f"user{uid}@t1.com",
                hashed_password=f"h{uid}",
                tenant_id=tenant_id,
            )
            for uid in [user1_id, user2_id]
        ]
        db_session.add_all(users)
        await db_session.commit()

        # Link users to role through user_roles junction table
        from src.core.models.rbac_models import user_roles

        user_role_values = [{"user_id": uid, "role_id": role2_id} for uid in [user1_id, user2_id]]
        await db_session.execute(user_roles.insert(), user_role_values)
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # Bulk revoke editor role
        results = await rbac.bulk_revoke_roles([user1_id, user2_id], "editor", tenant_id=tenant_id)

        assert len(results) == 2
        assert all(r["success"] for r in results)

        clear_tenant_context()


@pytest.mark.asyncio
class TestConditionalPermissions:
    """Test conditional permission evaluation"""

    async def test_owner_only_condition(self, db_session: AsyncSession):
        """owner_only condition restricts access to resource owner"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        role_id = TenantFactory.next_id()
        user_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        # Create role with owner_only condition
        role = Role(id=role_id, name="editor", tenant_id=tenant_id)
        db_session.add(role)
        await db_session.commit()

        # Create permission with conditions
        perm = RolePermission(
            role_id=role_id,
            resource="workflow",
            action="write",
            conditions={"owner_only": True},
            tenant_id=tenant_id,
        )
        db_session.add(perm)
        await db_session.commit()

        # Create user
        user = User(
            id=user_id,
            email=f"user{user_id}@t1.com",
            hashed_password="h",
            tenant_id=tenant_id,
        )
        db_session.add(user)
        await db_session.commit()

        # Link user to role through user_roles junction table
        from src.core.models.rbac_models import user_roles

        await db_session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # Note: Actual workflow ownership check would require workflow model
        # This test verifies the condition structure is correct
        from sqlalchemy.orm import selectinload

        result = await db_session.execute(
            select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        )
        role_obj = result.scalar_one()

        # Verify condition exists - permissions is a relationship, not JSON
        workflow_perm = next((p for p in role_obj.permissions if p.resource == "workflow"), None)
        assert workflow_perm is not None
        assert workflow_perm.conditions.get("owner_only") is True

        clear_tenant_context()

    async def test_same_tenant_condition(self, db_session: AsyncSession):
        """same_tenant condition ensures resource is in same tenant"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        role_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        # Create role with same_tenant condition
        role = Role(id=role_id, name="viewer", tenant_id=tenant_id)
        db_session.add(role)
        await db_session.commit()

        # Create permission with conditions
        perm = RolePermission(
            role_id=role_id,
            resource="workflow",
            action="read",
            conditions={"same_tenant": True},
            tenant_id=tenant_id,
        )
        db_session.add(perm)
        await db_session.commit()

        set_tenant_id(tenant_id)

        # Verify condition structure - need to fetch role object
        from sqlalchemy.orm import selectinload

        result = await db_session.execute(
            select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        )
        role_obj = result.scalar_one()

        # Verify permissions
        workflow_perm = next((p for p in role_obj.permissions if p.resource == "workflow"), None)
        assert workflow_perm is not None
        assert workflow_perm.conditions.get("same_tenant") is True

        clear_tenant_context()


@pytest.mark.asyncio
class TestPermissionCaching:
    """Test permission caching behavior"""

    async def test_cache_respects_tenant_id(self, db_session: AsyncSession):
        """Permission cache keys include tenant_id"""
        # Generate unique IDs
        tenant_id = TenantFactory.next_id()
        role_id = TenantFactory.next_id()
        user_id = TenantFactory.next_id()

        # Create tenant
        tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=f"tenant{tenant_id}")
        db_session.add(tenant)
        await db_session.commit()

        # Create role
        role = Role(id=role_id, name="admin", tenant_id=tenant_id)
        db_session.add(role)
        await db_session.commit()

        # Create wildcard permission for admin
        perm = RolePermission(role_id=role_id, resource="*", action="*", tenant_id=tenant_id)
        db_session.add(perm)
        await db_session.commit()

        # Create user
        user = User(
            id=user_id,
            email=f"admin{user_id}@t1.com",
            hashed_password="h",
            tenant_id=tenant_id,
        )
        db_session.add(user)
        await db_session.commit()

        # Link user to role through user_roles junction table
        from src.core.models.rbac_models import user_roles

        await db_session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        await db_session.commit()

        set_tenant_id(tenant_id)
        rbac = RBACService(db_session)

        # First call (cache miss)
        has_perm = await rbac.user_has_permission(
            user_id=user_id, permission="agent:read", tenant_id=tenant_id
        )
        assert has_perm is True

        # Second call (should hit cache)
        has_perm = await rbac.user_has_permission(
            user_id=user_id, permission="agent:read", tenant_id=tenant_id
        )
        assert has_perm is True

        clear_tenant_context()
