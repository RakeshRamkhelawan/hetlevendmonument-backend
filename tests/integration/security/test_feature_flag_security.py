import pytest
from sqlalchemy import select, text
from httpx import AsyncClient

from src.core.feature_flags import Feature
from src.core.feature_flags.models import FeatureFlag

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]


class TestFeatureFlagSecurity:
    """Security and tenant isolation validation for feature flags."""

    async def test_toggle_feature_requires_admin(
        self,
        async_client: AsyncClient,
        test_user_token: str,
    ) -> None:
        """Verify that a non-admin user is forbidden from toggling feature flags."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        response = await async_client.post(
            "/api/admin/features/memory_mcp/toggle?target_tenant_id=1",
            json={"enabled": True},
            headers=headers,
        )
        assert response.status_code == 403
        assert "admin" in response.json().get("detail", "").lower()

    async def test_toggle_feature_admin_success(
        self,
        async_client: AsyncClient,
        admin_token: str,
        postgres_session,
    ) -> None:
        """Verify that an admin can toggle feature flags for a tenant."""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Seed target tenant first to satisfy FK constraints
        from src.core.models.rbac_models import Tenant
        from src.core.database.tenant_query_filter import TenantFilterBypass
        with TenantFilterBypass():
            existing = await postgres_session.execute(select(Tenant).where(Tenant.id == 101))
            if existing.scalar_one_or_none() is None:
                postgres_session.add(
                    Tenant(
                        id=101,
                        name="Test Tenant 101",
                        slug="test-tenant-101",
                    )
                )
                await postgres_session.commit()
        
        # 1. Toggle ON
        response = await async_client.post(
            "/api/admin/features/memory_mcp/toggle?target_tenant_id=101",
            json={"enabled": True},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert response.json()["tenant_id"] == "101"

        # Verify DB entry exists (using bypass context since RLS is now enabled)
        from src.core.database.tenant_query_filter import TenantFilterBypass
        with TenantFilterBypass():
            await postgres_session.execute(text("SELECT set_config('app.current_tenant', '101', true)"))
            res = await postgres_session.execute(
                select(FeatureFlag).where(
                    FeatureFlag.tenant_id == 101,
                    FeatureFlag.feature_name == "memory_mcp"
                )
            )
            flag = res.scalar_one_or_none()
            assert flag is not None
            assert flag.is_enabled is True

        # 2. Toggle OFF
        response = await async_client.post(
            "/api/admin/features/memory_mcp/toggle?target_tenant_id=101",
            json={"enabled": False},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # Verify DB entry updated
        with TenantFilterBypass():
            await postgres_session.execute(text("SELECT set_config('app.current_tenant', '101', true)"))
            res = await postgres_session.execute(
                select(FeatureFlag).where(
                    FeatureFlag.tenant_id == 101,
                    FeatureFlag.feature_name == "memory_mcp"
                )
            )
            flag = res.scalar_one_or_none()
            assert flag is not None
            assert flag.is_enabled is False

    async def test_feature_flag_rls_isolation(
        self,
        postgres_session,
    ) -> None:
        """Verify that PostgreSQL RLS policy restricts cross-tenant database access."""
        from src.core.database.tenant_query_filter import TenantFilterBypass

        # Setup test feature flags for tenant 101 and tenant 102
        # Use TenantFilterBypass to insert records bypassing current_tenant context
        from src.core.models.rbac_models import Tenant
        with TenantFilterBypass():
            # Seed tenants 101 and 102 to satisfy FK constraints
            for tid in [101, 102]:
                existing = await postgres_session.execute(select(Tenant).where(Tenant.id == tid))
                if existing.scalar_one_or_none() is None:
                    postgres_session.add(
                        Tenant(
                            id=tid,
                            name=f"Test Tenant {tid}",
                            slug=f"test-tenant-{tid}",
                        )
                    )
            await postgres_session.commit()

            # Clean up potential leftovers
            await postgres_session.execute(
                text("DELETE FROM feature_flags WHERE tenant_id IN (101, 102)")
            )

            flag_a = FeatureFlag(
                tenant_id=101,
                feature_name="memory_mcp",
                is_enabled=True
            )
            flag_b = FeatureFlag(
                tenant_id=102,
                feature_name="memory_mcp",
                is_enabled=False
            )
            postgres_session.add_all([flag_a, flag_b])
            await postgres_session.commit()

        # Bootstrap RLS (not created by Base.metadata.create_all())
        await postgres_session.execute(text("ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY"))
        await postgres_session.execute(
            text("DROP POLICY IF EXISTS ff_tenant_isolation ON feature_flags")
        )
        await postgres_session.execute(
            text(
                "CREATE POLICY ff_tenant_isolation ON feature_flags "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )

        # Create a temporary test role to verify RLS properly (superuser bypasses RLS)
        await postgres_session.execute(text("DROP ROLE IF EXISTS rls_ff_tester"))
        await postgres_session.execute(text("CREATE ROLE rls_ff_tester NOLOGIN"))
        await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_ff_tester"))
        await postgres_session.execute(text("GRANT SELECT ON feature_flags TO rls_ff_tester"))

        try:
            # Query under tenant 101 RLS context
            await postgres_session.execute(text("SET ROLE rls_ff_tester"))
            await postgres_session.execute(text("SET app.current_tenant = '101'"))
            res_a = await postgres_session.execute(select(FeatureFlag))
            flags_a = res_a.scalars().all()
            # Tenant 101 should only see tenant 101 flag
            assert len(flags_a) == 1
            assert flags_a[0].tenant_id == 101

            # Query under tenant 102 RLS context
            await postgres_session.execute(text("SET ROLE rls_ff_tester"))
            await postgres_session.execute(text("SET app.current_tenant = '102'"))
            res_b = await postgres_session.execute(select(FeatureFlag))
            flags_b = res_b.scalars().all()
            # Tenant 102 should only see tenant 102 flag
            assert len(flags_b) == 1
            assert flags_b[0].tenant_id == 102

            # Query under an empty/unauthenticated context
            await postgres_session.execute(text("SET ROLE rls_ff_tester"))
            await postgres_session.execute(text("SET app.current_tenant = ''"))
            res_empty = await postgres_session.execute(select(FeatureFlag))
            flags_empty = res_empty.scalars().all()
            # Unauthenticated query should return zero records (fails secure)
            assert len(flags_empty) == 0
        finally:
            # Reset role and context to allow clean cleanup
            await postgres_session.execute(text("RESET ROLE"))
            await postgres_session.execute(text("RESET app.current_tenant"))

        # Clean up
        with TenantFilterBypass():
            await postgres_session.execute(
                text("DELETE FROM feature_flags WHERE tenant_id IN (101, 102)")
            )
            await postgres_session.commit()
