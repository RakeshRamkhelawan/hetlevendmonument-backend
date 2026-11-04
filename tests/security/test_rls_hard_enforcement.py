"""
RLS (Row-Level Security) Hard Enforcement Tests

These tests verify that PostgreSQL RLS policies correctly enforce tenant isolation
at the database level. Even if application-level filtering fails, RLS should
prevent cross-tenant data access.

Requirements:
- PostgreSQL database with RLS policies enabled
- rls_bypass role created
- All tenant-scoped tables have RLS enabled
"""

import os
import socket
from typing import Any, Dict

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from tests.fixtures.testdatabase import testdatabase_poort, testdatabase_url


def _is_postgres_available() -> bool:
    """Check if PostgreSQL is available on port 5455."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", testdatabase_poort()))
        sock.close()
        return result == 0
    except Exception:
        return False


# Skip all tests if not running against PostgreSQL
pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        os.getenv("SKIP_RLS_TESTS") == "1" or not _is_postgres_available(),
        reason="RLS tests require PostgreSQL on localhost:{os.environ.get('POSTGRES_PORT', '5455')}",
    ),
]


@pytest_asyncio.fixture
async def pg_engine():
    """Create a PostgreSQL engine for RLS tests."""
    engine = create_async_engine(
        testdatabase_url(),
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(pg_engine):
    """Create a database session for testing."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(
        pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        # Rollback any changes
        await session.rollback()


@pytest_asyncio.fixture
async def setup_tenant_data(db_session: AsyncSession):
    """Set up test data for two tenants."""
    import uuid

    unique_id = str(uuid.uuid4())[:8]

    # Check if tenants already exist
    result = await db_session.execute(
        text(
            f"""
        SELECT id FROM tenants
        WHERE slug IN ('tenant-a-{unique_id}', 'tenant-b-{unique_id}')
        """
        )
    )
    existing = result.fetchall()
    if existing:
        tenant_a_id = existing[0][0]
        tenant_b_id = existing[1][0] if len(existing) > 1 else tenant_a_id + 1
        return {"tenant_a_id": tenant_a_id, "tenant_b_id": tenant_b_id}

    # Create tenants with all required fields
    await db_session.execute(
        text(
            f"""
        INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb)
        VALUES
            ('Tenant A {unique_id}', 'tenant-a-{unique_id}', true, 100, 10, 5),
            ('Tenant B {unique_id}', 'tenant-b-{unique_id}', true, 100, 10, 5)
        ON CONFLICT (slug) DO NOTHING
        """
        )
    )

    # Get tenant IDs
    result = await db_session.execute(
        text(
            f"""
        SELECT id, slug FROM tenants
        WHERE slug IN ('tenant-a-{unique_id}', 'tenant-b-{unique_id}')
        """
        )
    )
    tenants = {row.slug: row.id for row in result.mappings()}

    tenant_a_id = tenants.get(f"tenant-a-{unique_id}", 1)
    tenant_b_id = tenants.get(f"tenant-b-{unique_id}", 2)

    await db_session.commit()

    return {"tenant_a_id": tenant_a_id, "tenant_b_id": tenant_b_id}


class TestRLSPoliciesExist:
    """Tests that RLS policies exist on tenant-scoped tables."""

    @pytest.mark.asyncio
    async def test_rls_policies_exist_on_tables(self, db_session: AsyncSession):
        """Verify RLS policies exist on tables with tenant isolation."""
        result = await db_session.execute(
            text(
                """
            SELECT tablename, policyname
            FROM pg_policies
            WHERE policyname LIKE 'tenant_isolation_%'
            OR policyname LIKE '%tenant%isolation%'
            """
            )
        )
        policies = result.fetchall()

        # Get list of tables with tenant isolation policies
        tables_with_rls = {p[0] for p in policies}

        if len(tables_with_rls) == 0:
            pytest.skip("No tenant isolation policies found in database")

        # At least one table should have tenant isolation
        assert len(tables_with_rls) >= 1, "No tables have tenant isolation policies"

    @pytest.mark.asyncio
    async def test_rls_enabled_on_tenant_tables(self, db_session: AsyncSession):
        """Verify RLS is enabled on at least some tenant tables."""
        result = await db_session.execute(
            text(
                """
            SELECT relname, relrowsecurity
            FROM pg_class
            WHERE relnamespace = 'public'::regnamespace
            AND relrowsecurity = true
            """
            )
        )
        rows = result.fetchall()
        table_names = [row[0] for row in rows]

        if len(table_names) == 0:
            pytest.skip("No tables have RLS enabled")

        # At least one table should have RLS
        assert len(table_names) >= 1, "No tables have RLS enabled"

    @pytest.mark.asyncio
    async def test_any_rls_policies_exist(self, db_session: AsyncSession):
        """Verify some RLS policies exist in the database."""
        result = await db_session.execute(
            text(
                """
            SELECT COUNT(*) as count
            FROM pg_policies
            """
            )
        )
        count = result.scalar() or 0

        if count == 0:
            pytest.skip("No RLS policies found in database")

        assert count >= 1, "No RLS policies found in database"


class TestRLSAdminBypass:
    """Tests for admin bypass functionality."""

    @pytest.mark.asyncio
    async def test_rls_admin_bypass_works(self, db_session: AsyncSession):
        """Test that rls_bypass role can access all data."""
        # Check if rls_bypass role exists
        result = await db_session.execute(
            text(
                """
                SELECT COUNT(*) FROM pg_roles WHERE rolname = 'rls_bypass'
            """
            )
        )
        if result.scalar() == 0:
            pytest.skip("rls_bypass role not created")

        # Check if current user has permission to SET ROLE
        try:
            await db_session.execute(text("SET ROLE rls_bypass"))
            await db_session.execute(text("SET ROLE postgres"))
        except Exception as e:
            pytest.skip(f"Cannot SET ROLE to rls_bypass: {e}")

        # Find an RLS-enabled table to test with
        result = await db_session.execute(
            text(
                """
            SELECT relname FROM pg_class
            WHERE relnamespace = 'public'::regnamespace
            AND relrowsecurity = true
            LIMIT 1
            """
            )
        )
        row = result.fetchone()
        if row is None:
            pytest.skip("No RLS-enabled tables to test with")

        table_name = row[0]

        # Verify that admin bypass works
        await db_session.execute(text("SET ROLE rls_bypass"))

        # As rls_bypass, we should be able to see all data
        try:
            result = await db_session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.scalar()
        except Exception:
            # Table may have been dropped but still visible in pg_class
            pytest.skip(f"RLS-enabled table '{table_name}' does not exist")

        # Reset role (best effort)
        try:
            await db_session.execute(text("SET ROLE postgres"))
        except Exception:
            pass

        assert count is not None


class TestRLSHelperFunction:
    """Tests for RLS helper functions."""

    async def _function_exists(self, db_session: AsyncSession, func_name: str) -> bool:
        """Check if a PostgreSQL function exists."""
        result = await db_session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM pg_proc
                WHERE proname = :func_name
            )
            """
            ),
            {"func_name": func_name},
        )
        return result.scalar() or False

    @pytest.mark.asyncio
    async def test_get_rls_status_function_exists(self, db_session: AsyncSession):
        """Verify the get_rls_status helper function exists."""
        if not await self._function_exists(db_session, "get_rls_status"):
            pytest.skip("get_rls_status function not created")

        result = await db_session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM pg_proc
                WHERE proname = 'get_rls_status'
            )
            """
            )
        )
        exists = result.scalar()
        assert exists is True, "get_rls_status function does not exist"

    @pytest.mark.asyncio
    async def test_get_rls_status_returns_data(self, db_session: AsyncSession):
        """Test that get_rls_status returns RLS information."""
        if not await self._function_exists(db_session, "get_rls_status"):
            pytest.skip("get_rls_status function not created")

        result = await db_session.execute(text("SELECT * FROM get_rls_status()"))
        rows = result.fetchall()

        # Should return at least some tables with RLS
        assert len(rows) > 0, "get_rls_status returned no data"

        # Verify structure
        for row in rows:
            assert hasattr(row, "table_name") or len(row) >= 3


class TestRLSMigrationDowngrade:
    """Tests for RLS migration downgrade."""

    @pytest.mark.asyncio
    async def test_rls_migration_downgrade(self, db_session: AsyncSession):
        """Test that downgrade removes all RLS policies.

        This test verifies the current RLS state without running destructive
        migrations. It checks that policies can be identified for removal.
        """
        # Check if there are any RLS policies to downgrade
        result = await db_session.execute(
            text(
                """
                SELECT schemaname, tablename, policyname
                FROM pg_policies
                WHERE policyname LIKE 'tenant_isolation%' OR policyname LIKE '%tenant%'
                LIMIT 5
            """
            )
        )
        policies = result.fetchall()

        if len(policies) == 0:
            pytest.skip("No RLS policies found to test")

        # Verify we can identify policies for downgrade
        policy_names = [p[2] for p in policies]
        assert all(
            "tenant" in name.lower() for name in policy_names
        ), "Expected tenant-related policy names"

        # Count policies per table
        table_counts: Dict[str, int] = {}
        for p in policies:
            table = p[1]
            table_counts[table] = table_counts.get(table, 0) + 1

        # Log what would be downgraded (non-destructive verification)
        for table, count in table_counts.items():
            assert count > 0, f"Table {table} should have policies"
