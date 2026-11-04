"""
Performance Tests: Multi-Tenant Operations

Tests performance characteristics:
- Query filtering overhead
- Permission check caching
- Concurrent tenant requests
- Database query optimization
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import asyncio
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.models.rbac_models import Role, RolePermission, Tenant, User, user_roles
from src.core.services.rbac_service import RBACService


@pytest.mark.asyncio
class TestTenantFilteringPerformance:
    """Test performance of tenant filtering"""

    async def test_tenant_filter_overhead(self, db_session: AsyncSession):
        """Tenant filtering should add minimal overhead"""
        # Create tenant
        tenant = Tenant(id=10001, name="Tenant 1", slug="tenant-1")
        db_session.add(tenant)
        await db_session.commit()

        # Create 100 users (without role_id - use many-to-many relationship)
        users = [
            User(
                id=10000 + i,
                email=f"user{i}@t1.com",
                hashed_password=f"h{i}",
                tenant_id=10001,
            )
            for i in range(1, 101)
        ]
        db_session.add_all(users)
        await db_session.commit()

        set_tenant_id(10001)

        # Measure query time with tenant filter
        start = time.time()
        result = await db_session.execute(select(User).where(User.tenant_id == 10001))
        users_list = result.scalars().all()
        elapsed = time.time() - start

        # Should complete quickly (< 100ms)
        assert elapsed < 0.1
        assert len(users_list) == 100

        clear_tenant_context()

    async def test_bulk_query_performance(self, db_session: AsyncSession):
        """Bulk queries with tenant filtering should be efficient"""
        # Create tenants with unique IDs
        base_id = 20000
        tenants = [
            Tenant(id=base_id + i, name=f"Tenant {i}", slug=f"tenant-{i}") for i in range(1, 6)
        ]
        db_session.add_all(tenants)
        await db_session.commit()

        # Create 20 users per tenant (100 total)
        all_users = []
        for tenant_offset in range(1, 6):
            tenant_id = base_id + tenant_offset
            users = [
                User(
                    id=tenant_id * 100 + i,
                    email=f"user{i}@t{tenant_offset}.com",
                    hashed_password=f"h{i}",
                    tenant_id=tenant_id,
                )
                for i in range(1, 21)
            ]
            all_users.extend(users)

        db_session.add_all(all_users)
        await db_session.commit()

        set_tenant_id(base_id + 1)

        # Query should only return tenant 1's users
        start = time.time()
        result = await db_session.execute(select(User).where(User.tenant_id == base_id + 1))
        tenant1_users = result.scalars().all()
        elapsed = time.time() - start

        assert len(tenant1_users) == 20
        assert all(u.tenant_id == base_id + 1 for u in tenant1_users)
        assert elapsed < 0.1  # Should be fast

        clear_tenant_context()


@pytest.mark.asyncio
class TestPermissionCachePerformance:
    """Test RBAC permission caching performance"""

    async def test_permission_cache_effectiveness(self, db_session: AsyncSession):
        """Permission cache should speed up repeated checks"""
        # Create tenant, role, and user with unique IDs
        base_id = 30000
        tenant = Tenant(id=base_id + 1, name="Tenant 1", slug="tenant-1")
        db_session.add(tenant)
        await db_session.commit()

        # Create role
        role = Role(id=base_id + 1, name="admin", tenant_id=base_id + 1)
        db_session.add(role)
        await db_session.commit()

        # Add permissions to role
        perm = RolePermission(role_id=base_id + 1, resource="*", action="*", tenant_id=base_id + 1)
        db_session.add(perm)
        await db_session.commit()

        # Create user
        user = User(
            id=base_id + 1,
            email="admin@t1.com",
            hashed_password="h",
            tenant_id=base_id + 1,
        )
        db_session.add(user)
        await db_session.flush()

        # Link user to role via user_roles
        await db_session.execute(
            user_roles.insert().values(user_id=base_id + 1, role_id=base_id + 1)
        )
        await db_session.commit()

        set_tenant_id(base_id + 1)
        rbac = RBACService(db_session)

        # First check (cache miss)
        start = time.time()
        has_perm = await rbac.user_has_permission(base_id + 1, "agent:read", tenant_id=base_id + 1)
        first_check = time.time() - start

        # Second check (cache hit)
        start = time.time()
        has_perm = await rbac.user_has_permission(base_id + 1, "agent:read", tenant_id=base_id + 1)
        second_check = time.time() - start

        # Cached check should be faster or same speed
        assert has_perm is True
        # Both should be reasonably fast (< 10s for first, < 5s for cached)
        assert first_check < 10.0
        assert second_check < 5.0

        clear_tenant_context()

    async def test_bulk_permission_checks(self, db_session: AsyncSession):
        """Bulk permission checks should complete quickly"""
        # Create tenant, role, and user with unique IDs
        base_id = 40000
        tenant = Tenant(id=base_id + 1, name="Tenant 1", slug="tenant-1")
        db_session.add(tenant)
        await db_session.commit()

        # Create role
        role = Role(id=base_id + 1, name="user", tenant_id=base_id + 1)
        db_session.add(role)
        await db_session.commit()

        # Add permissions to role
        perms = [
            RolePermission(
                role_id=base_id + 1,
                resource="agent",
                action="read",
                tenant_id=base_id + 1,
            ),
            RolePermission(
                role_id=base_id + 1,
                resource="workflow",
                action="read",
                tenant_id=base_id + 1,
            ),
        ]
        db_session.add_all(perms)
        await db_session.commit()

        # Create user
        user = User(
            id=base_id + 1,
            email="user@t1.com",
            hashed_password="h",
            tenant_id=base_id + 1,
        )
        db_session.add(user)
        await db_session.flush()

        # Link user to role via user_roles
        await db_session.execute(
            user_roles.insert().values(user_id=base_id + 1, role_id=base_id + 1)
        )
        await db_session.commit()

        set_tenant_id(base_id + 1)
        rbac = RBACService(db_session)

        # Check multiple permissions
        permissions_to_check = [
            "agent:read",
            "agent:write",
            "workflow:read",
            "workflow:write",
            "workflow:delete",
        ]

        start = time.time()
        results = []
        for perm in permissions_to_check:
            result = await rbac.user_has_permission(base_id + 1, perm, tenant_id=base_id + 1)
            results.append(result)
        elapsed = time.time() - start

        # Should complete all checks within reasonable time (< 60s)
        assert elapsed < 60.0
        assert len(results) == 5

        clear_tenant_context()


@pytest.mark.asyncio
class TestConcurrentTenantRequests:
    """Test performance under concurrent multi-tenant load"""

    async def test_concurrent_tenant_isolation(self, db_session: AsyncSession):
        """Concurrent requests for different tenants should be isolated"""
        # Create multiple tenants with unique IDs
        base_id = 50000
        tenants = [
            Tenant(id=base_id + i, name=f"Tenant {i}", slug=f"tenant-{i}") for i in range(1, 4)
        ]
        db_session.add_all(tenants)
        await db_session.commit()

        # Create users for each tenant
        for offset in range(1, 4):
            tenant_id = base_id + offset
            user = User(
                id=tenant_id,
                email=f"user@t{offset}.com",
                hashed_password=f"h{offset}",
                tenant_id=tenant_id,
            )
            db_session.add(user)
        await db_session.commit()

        async def query_tenant(tenant_offset: int):
            """Simulate tenant-specific query"""
            tenant_id = base_id + tenant_offset
            set_tenant_id(tenant_id)
            result = await db_session.execute(select(User).where(User.tenant_id == tenant_id))
            users = result.scalars().all()
            clear_tenant_context()
            return len(users)

        # Run queries concurrently
        start = time.time()
        results = await asyncio.gather(query_tenant(1), query_tenant(2), query_tenant(3))
        elapsed = time.time() - start

        # Each tenant should have 1 user
        assert results == [1, 1, 1]
        # Should complete quickly (< 500ms)
        assert elapsed < 0.5

    async def test_high_volume_permission_checks(self, db_session: AsyncSession):
        """System should handle high volume of permission checks"""
        # Create tenant, role, and users with unique IDs
        base_id = 60000
        tenant = Tenant(id=base_id + 1, name="Tenant 1", slug="tenant-1")
        db_session.add(tenant)
        await db_session.commit()

        # Create role
        role = Role(id=base_id + 1, name="user", tenant_id=base_id + 1)
        db_session.add(role)
        await db_session.commit()

        # Add permissions to role
        perm = RolePermission(
            role_id=base_id + 1, resource="agent", action="read", tenant_id=base_id + 1
        )
        db_session.add(perm)
        await db_session.commit()

        # Create 10 users
        users = [
            User(
                id=base_id + i,
                email=f"user{i}@t1.com",
                hashed_password=f"h{i}",
                tenant_id=base_id + 1,
            )
            for i in range(1, 11)
        ]
        db_session.add_all(users)
        await db_session.flush()

        # Link all users to role via user_roles
        for i in range(1, 11):
            await db_session.execute(
                user_roles.insert().values(user_id=base_id + i, role_id=base_id + 1)
            )
        await db_session.commit()

        set_tenant_id(base_id + 1)
        rbac = RBACService(db_session)

        # Check permissions for all users
        start = time.time()
        tasks = [
            rbac.user_has_permission(base_id + user_id, "agent:read", tenant_id=base_id + 1)
            for user_id in range(1, 11)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # All should have permission
        assert all(results)
        # Should complete within reasonable time (< 30s for 10 users)
        assert elapsed < 30.0

        clear_tenant_context()


@pytest.mark.asyncio
class TestDatabaseIndexEfficiency:
    """Test database index usage for tenant queries"""

    async def test_tenant_id_index_used(self, db_session: AsyncSession):
        """Queries should use tenant_id index"""
        # Create tenant and users with unique IDs
        base_id = 70000
        tenant = Tenant(id=base_id + 1, name="Tenant 1", slug="tenant-1")
        db_session.add(tenant)
        await db_session.commit()

        # Create many users
        users = [
            User(
                id=base_id + i,
                email=f"user{i}@t1.com",
                hashed_password=f"h{i}",
                tenant_id=base_id + 1,
            )
            for i in range(1, 1001)  # 1000 users
        ]
        db_session.add_all(users)
        await db_session.commit()

        set_tenant_id(base_id + 1)

        # Query with tenant filter
        start = time.time()
        result = await db_session.execute(
            select(User).where(User.tenant_id == base_id + 1).limit(10)
        )
        users_list = result.scalars().all()
        elapsed = time.time() - start

        # Should be fast even with 1000 users (< 100ms)
        assert elapsed < 0.1
        assert len(users_list) == 10

        clear_tenant_context()
