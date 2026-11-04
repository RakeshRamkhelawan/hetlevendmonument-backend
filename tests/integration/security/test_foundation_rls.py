"""Security integration tests for Foundation Portal Row-Level Security.

Validates that RLS policies correctly isolate tenant data across all
Foundation Portal tables that have a tenant_id column.

ContentTag is explicitly excluded (no tenant_id; isolation via JOIN only).

NOTE: The test session fixture uses Base.metadata.create_all() which does NOT
create RLS policies. Each test bootstraps the policies it needs, ensuring
isolation and no side effects across tests.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
class TestFoundationRLSEnforcement:
    """Penetration-style RLS tests for Foundation Portal tables."""

    _RLS_TABLES = [
        "portal_users",
        "magic_link_tokens",
        "foundation_content",
        "foundation_portal_settings",
        "takedown_requests",
        "newsletter_subscriptions",
        "educational_access",
        "study_collections",
        "foundation_contact_submissions",
        "foundation_donations",
    ]

    async def _seed_tenant_b(self, session: AsyncSession) -> int:
        await session.execute(
            text(
                "INSERT INTO tenants (id, name, slug, domain, is_active, "
                "max_users, max_agents, max_storage_gb, subscription_tier, "
                "subscription_status) VALUES (:id, 'Tenant B', 'tenant-b', "
                "'b.local', true, 100, 100, 100.0, 'enterprise', 'active') "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": 2},
        )
        return 2

    async def _bootstrap_rls(self, session: AsyncSession) -> None:
        """Enable RLS and create policies for Foundation tables.

        Policies are created idempotently (drop-before-create) because
        PostgreSQL DDL causes implicit commits that may survive a
        partially-rolled-back transaction from a previous test run.
        """
        for tbl in self._RLS_TABLES:
            await session.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
            await session.execute(text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY"))
            await session.execute(text(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}"))
            await session.execute(
                text(
                    f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
                    f"FOR ALL USING ("
                    f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                    f")"
                )
            )

    async def _create_rls_tester_role(self, session: AsyncSession) -> None:
        await session.execute(text("DROP ROLE IF EXISTS rls_tester"))
        await session.execute(text("CREATE ROLE rls_tester NOLOGIN"))
        await session.execute(text("GRANT USAGE ON SCHEMA public TO rls_tester"))
        for tbl in self._RLS_TABLES:
            await session.execute(text(f"GRANT SELECT ON {tbl} TO rls_tester"))

    async def _drop_rls_tester_role(self, session: AsyncSession) -> None:
        await session.execute(text("REASSIGN OWNED BY rls_tester TO postgres"))
        await session.execute(text("DROP OWNED BY rls_tester"))
        await session.execute(text("DROP ROLE IF EXISTS rls_tester"))

    async def test_portal_users_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO portal_users (tenant_id, email, is_verified, is_blocked, role, "
                "email_verified, consent_given) "
                "VALUES (:ta, 'a@test.com', true, false, 'visitor', false, false), "
                "(:tb, 'b@test.com', true, false, 'visitor', false, false)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, email FROM portal_users")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_magic_link_tokens_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO portal_users (id, tenant_id, email, is_verified, is_blocked, role, "
                "email_verified, consent_given) "
                "VALUES (1, :ta, 'a@test.com', true, false, 'visitor', false, false), "
                "(2, :tb, 'b@test.com', true, false, 'visitor', false, false)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.execute(
            text(
                "INSERT INTO magic_link_tokens (tenant_id, portal_user_id, token_hash, "
                "expires_at) VALUES (:ta, 1, 'hash_a', NOW() + INTERVAL '1 hour'), "
                "(:tb, 2, 'hash_b', NOW() + INTERVAL '1 hour')"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, token_hash FROM magic_link_tokens")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_foundation_content_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO foundation_content (tenant_id, type, title_nl, language, "
                "privacy, status, rights_confirmed, ai_tagging_failed, is_anonymous) "
                "VALUES (:ta, 'STORY', 'Titel A', 'nl', 'PUBLIC', 'PENDING', true, false, false), "
                "(:tb, 'ARTWORK', 'Titel B', 'nl', 'PUBLIC', 'PENDING', true, false, false)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, title_nl FROM foundation_content")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_foundation_portal_settings_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO foundation_portal_settings (tenant_id, platform_name_nl, "
                "primary_color, accent_color) "
                "VALUES (:ta, 'Platform A', '#000000', '#ffffff'), "
                "(:tb, 'Platform B', '#111111', '#eeeeee')"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, platform_name_nl FROM foundation_portal_settings")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_takedown_requests_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO foundation_content (id, tenant_id, type, title_nl, language, "
                "privacy, status, rights_confirmed, ai_tagging_failed, is_anonymous) "
                "VALUES (1, :ta, 'STORY', 'Titel A', 'nl', 'PUBLIC', 'APPROVED', true, false, false), "
                "(2, :tb, 'STORY', 'Titel B', 'nl', 'PUBLIC', 'APPROVED', true, false, false)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.execute(
            text(
                "INSERT INTO takedown_requests (tenant_id, content_id, requester_email, "
                "requester_name, legal_basis, status) "
                "VALUES (:ta, 1, 'a@test.com', 'A', 'copyright', 'PENDING'), "
                "(:tb, 2, 'b@test.com', 'B', 'copyright', 'PENDING')"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, requester_email FROM takedown_requests")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_newsletter_subscriptions_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO newsletter_subscriptions (tenant_id, email, status, "
                "unsubscribe_token_hash) "
                "VALUES (:ta, 'a@test.com', 'SUBSCRIBED', 'hash_a'), "
                "(:tb, 'b@test.com', 'SUBSCRIBED', 'hash_b')"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, email FROM newsletter_subscriptions")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_educational_access_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        hash_a = "a" * 64
        hash_b = "b" * 64
        await postgres_session.execute(
            text(
                "INSERT INTO educational_access (tenant_id, email, code_hash, role, is_active) "
                "VALUES (:ta, 'teacher_a@school.nl', :ha, 'teacher', true), "
                "(:tb, 'teacher_b@school.nl', :hb, 'teacher', true)"
            ),
            {"ta": tenant_a, "tb": tenant_b, "ha": hash_a, "hb": hash_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, email FROM educational_access")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_study_collections_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        hash_c = "c" * 64
        hash_d = "d" * 64
        # First insert parent educational_access rows
        await postgres_session.execute(
            text(
                "INSERT INTO educational_access (id, tenant_id, email, code_hash, role, is_active) "
                "VALUES (101, :ta, 'teacher_a@school.nl', :hc, 'teacher', true), "
                "(102, :tb, 'teacher_b@school.nl', :hd, 'teacher', true)"
            ),
            {"ta": tenant_a, "tb": tenant_b, "hc": hash_c, "hd": hash_d},
        )
        await postgres_session.execute(
            text(
                "INSERT INTO study_collections (tenant_id, name, educational_access_id) "
                "VALUES (:ta, 'Collection A', 101), "
                "(:tb, 'Collection B', 102)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, name FROM study_collections")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_contact_submissions_rls_blocks_cross_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        """Tenant A cannot see Tenant B's contact submissions."""
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO foundation_contact_submissions (tenant_id, reference_number, name, email, subject, category, message) "
                "VALUES (:ta, 'CON-20260915-AAAA', 'Jan A', 'jan@a.nl', 'Vraag A', 'general', 'Bericht A'), "
                "(:tb, 'CON-20260915-BBBB', 'Piet B', 'piet@b.nl', 'Vraag B', 'general', 'Bericht B')"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, reference_number FROM foundation_contact_submissions")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_donations_rls_blocks_cross_tenant(self, postgres_session: AsyncSession) -> None:
        """Tenant A cannot see Tenant B's donations."""
        tenant_a = 1
        tenant_b = await self._seed_tenant_b(postgres_session)
        await self._bootstrap_rls(postgres_session)

        await postgres_session.execute(
            text(
                "INSERT INTO foundation_donations (tenant_id, email, amount_cents, currency, frequency, status, stripe_session_id, is_anonymous) "
                "VALUES (:ta, 'donor@a.nl', 2500, 'EUR', 'once', 'completed', 'sess_a_123', false), "
                "(:tb, 'donor@b.nl', 5000, 'EUR', 'once', 'completed', 'sess_b_456', false)"
            ),
            {"ta": tenant_a, "tb": tenant_b},
        )
        await postgres_session.flush()

        await self._create_rls_tester_role(postgres_session)
        await postgres_session.execute(text("SET ROLE rls_tester"))
        await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a}'"))

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, amount_cents FROM foundation_donations")
            )
            rows = result.fetchall()
            tenant_ids = [r.tenant_id for r in rows]
            assert tenant_a in tenant_ids
            assert tenant_b not in tenant_ids
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await self._drop_rls_tester_role(postgres_session)

    async def test_force_rls_is_active_on_all_foundation_tables(
        self, postgres_session: AsyncSession
    ) -> None:
        """All Foundation tables must have FORCE ROW LEVEL SECURITY enabled (relforcerowsecurity=true)."""
        await self._bootstrap_rls(postgres_session)

        stmt = text(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class "
            "WHERE relname = ANY(:tables)"
        )
        res = await postgres_session.execute(stmt, {"tables": self._RLS_TABLES})
        rows = {r.relname: (r.relrowsecurity, r.relforcerowsecurity) for r in res.fetchall()}

        for table in self._RLS_TABLES:
            assert table in rows, f"Table {table} missing in pg_class"
            has_rls, has_force_rls = rows[table]
            assert has_rls is True, f"Table {table} does not have ROW LEVEL SECURITY enabled"
            assert has_force_rls is True, (
                f"Table {table} does not have FORCE ROW LEVEL SECURITY enabled"
            )


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
class TestFoundationRLSDenyByDefault:
    """Verify RLS denies access when app.current_tenant is not set."""

    async def test_no_tenant_variable_returns_no_rows(self, postgres_session: AsyncSession) -> None:
        tenant_a = 1

        await postgres_session.execute(
            text(
                "INSERT INTO newsletter_subscriptions (tenant_id, email, status, "
                "unsubscribe_token_hash) "
                "VALUES (:ta, 'a@test.com', 'SUBSCRIBED', 'hash_a')"
            ),
            {"ta": tenant_a},
        )
        await postgres_session.flush()

        # Bootstrap RLS for newsletter_subscriptions only
        await postgres_session.execute(
            text("ALTER TABLE newsletter_subscriptions ENABLE ROW LEVEL SECURITY")
        )
        await postgres_session.execute(
            text(
                "CREATE POLICY newsletter_subscriptions_tenant_isolation "
                "ON newsletter_subscriptions FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )

        await postgres_session.execute(text("DROP ROLE IF EXISTS rls_tester"))
        await postgres_session.execute(text("CREATE ROLE rls_tester NOLOGIN"))
        await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_tester"))
        await postgres_session.execute(
            text("GRANT SELECT ON newsletter_subscriptions TO rls_tester")
        )

        await postgres_session.execute(text("SET ROLE rls_tester"))
        # Do NOT set app.current_tenant

        try:
            result = await postgres_session.execute(
                text("SELECT tenant_id, email FROM newsletter_subscriptions")
            )
            rows = result.fetchall()
            assert len(rows) == 0, "SECURITY FAIL: Rows returned without tenant context!"
        finally:
            await postgres_session.execute(text("RESET ROLE"))
            await postgres_session.execute(text("REASSIGN OWNED BY rls_tester TO postgres"))
            await postgres_session.execute(text("DROP OWNED BY rls_tester"))
            await postgres_session.execute(text("DROP ROLE IF EXISTS rls_tester"))
