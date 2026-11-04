"""
Twin RLS Isolation Tests — ADR-005 / ADR-026 §3.

Verify that PostgreSQL RLS policies on the Digital Twin tables enforce
strict tenant isolation at the database level.  Even if the application
layer omits a WHERE clause, RLS must block cross-tenant reads.

Tables under test:
    user_behavior_observations
    user_cognitive_profiles
    user_twin_consent

Requirements:
    PostgreSQL on localhost:{os.environ.get('POSTGRES_PORT', '5455')} with all twin RLS migrations applied.
"""

import os
import socket
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.fixtures.testdatabase import testdatabase_poort

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------


def _postgres_available() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("localhost", testdatabase_poort()))
        s.close()
        return result == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        os.getenv("SKIP_RLS_TESTS") == "1" or not _postgres_available(),
        reason="Twin RLS tests require PostgreSQL on localhost:{os.environ.get('POSTGRES_PORT', '5455')}",
    ),
]

# NOTE: must connect as non-superuser — PostgreSQL superusers always bypass RLS
# regardless of FORCE ROW LEVEL SECURITY. The sanskritisetu_app user has no
# SUPERUSER or BYPASSRLS privileges, so RLS policies are enforced correctly.
_DB_URL = f"postgresql+asyncpg://sanskritisetu_app:sanskritisetu_app@localhost:{testdatabase_poort()}/sanskritisetu"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(_DB_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(pg_engine):
    factory = async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def tenants(session: AsyncSession):
    """Create two isolated tenants, return their IDs."""
    uid = uuid.uuid4().hex[:8]
    await session.execute(
        text(
            f"""
            INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb)
            VALUES
                ('TwinRLS A {uid}', 'twin-rls-a-{uid}', true, 10, 5, 1),
                ('TwinRLS B {uid}', 'twin-rls-b-{uid}', true, 10, 5, 1)
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )
    result = await session.execute(
        text(f"SELECT id, slug FROM tenants WHERE slug IN ('twin-rls-a-{uid}', 'twin-rls-b-{uid}')")
    )
    ids = {row.slug: row.id for row in result.mappings()}
    await session.commit()
    return {
        "a": ids[f"twin-rls-a-{uid}"],
        "b": ids[f"twin-rls-b-{uid}"],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTwinRLSIsolation:
    """RLS blocks cross-tenant reads on all three twin tables."""

    @pytest.mark.asyncio
    async def test_behavior_observations_isolated_between_tenants(
        self, session: AsyncSession, tenants: dict
    ):
        """Tenant B must not see Tenant A's behavior observations."""
        ta, tb = tenants["a"], tenants["b"]
        hashed_uid = f"hashed-user-{uuid.uuid4().hex[:12]}"

        # Write observation under tenant A (bypass RLS with explicit SET)
        await session.execute(text(f"SET app.current_tenant = '{ta}'"))
        await session.execute(
            text(
                """
                INSERT INTO user_behavior_observations
                    (tenant_id, human_user_id, session_id, behavior_type, context,
                     outcome_metrics, confidence_score)
                VALUES
                    (:tid, :uid, :sid, 'file_edit', '{}', '{}', 0.9)
                """
            ).bindparams(tid=ta, uid=hashed_uid, sid=uuid.uuid4().hex)
        )
        await session.flush()

        # Switch context to tenant B — RLS must hide tenant A's row
        await session.execute(text(f"SET app.current_tenant = '{tb}'"))
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM user_behavior_observations WHERE human_user_id = :uid"
            ).bindparams(uid=hashed_uid)
        )
        count = result.scalar_one()
        assert count == 0, (
            f"Tenant B ({tb}) read {count} observation(s) belonging to Tenant A ({ta})"
        )

    @pytest.mark.asyncio
    async def test_cognitive_profiles_isolated_between_tenants(
        self, session: AsyncSession, tenants: dict
    ):
        """Tenant B must not see Tenant A's cognitive profile."""
        ta, tb = tenants["a"], tenants["b"]
        raw_uid = f"user-{uuid.uuid4().hex[:12]}"

        await session.execute(text(f"SET app.current_tenant = '{ta}'"))
        await session.execute(
            text(
                """
                INSERT INTO user_cognitive_profiles (tenant_id, human_user_id)
                VALUES (:tid, :uid)
                ON CONFLICT (tenant_id, human_user_id) DO NOTHING
                """
            ).bindparams(tid=ta, uid=raw_uid)
        )
        await session.flush()

        await session.execute(text(f"SET app.current_tenant = '{tb}'"))
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM user_cognitive_profiles WHERE human_user_id = :uid"
            ).bindparams(uid=raw_uid)
        )
        count = result.scalar_one()
        assert count == 0, f"Tenant B ({tb}) read {count} profile(s) belonging to Tenant A ({ta})"

    @pytest.mark.asyncio
    async def test_consent_records_isolated_between_tenants(
        self, session: AsyncSession, tenants: dict
    ):
        """Tenant B must not see Tenant A's consent record."""
        ta, tb = tenants["a"], tenants["b"]
        raw_uid = f"user-{uuid.uuid4().hex[:12]}"

        await session.execute(text(f"SET app.current_tenant = '{ta}'"))
        await session.execute(
            text(
                """
                INSERT INTO user_twin_consent
                    (tenant_id, human_user_id, consent_given, consent_version,
                     behavior_tracking, profile_aggregation, ai_interventions,
                     cross_session_memory)
                VALUES (:tid, :uid, true, '1.0', true, true, true, true)
                ON CONFLICT (tenant_id, human_user_id) DO NOTHING
                """
            ).bindparams(tid=ta, uid=raw_uid)
        )
        await session.flush()

        await session.execute(text(f"SET app.current_tenant = '{tb}'"))
        result = await session.execute(
            text("SELECT COUNT(*) FROM user_twin_consent WHERE human_user_id = :uid").bindparams(
                uid=raw_uid
            )
        )
        count = result.scalar_one()
        assert count == 0, (
            f"Tenant B ({tb}) read {count} consent record(s) belonging to Tenant A ({ta})"
        )

    @pytest.mark.asyncio
    async def test_rls_blocks_cross_tenant_hard_delete(self, session: AsyncSession, tenants: dict):
        """A DELETE with tenant B context must not erase tenant A's consent."""
        ta, tb = tenants["a"], tenants["b"]
        raw_uid = f"user-{uuid.uuid4().hex[:12]}"

        # Insert consent for tenant A (admin bypass — no SET needed at insert time
        # because the INSERT supplies tenant_id explicitly)
        await session.execute(text(f"SET app.current_tenant = '{ta}'"))
        await session.execute(
            text(
                """
                INSERT INTO user_twin_consent
                    (tenant_id, human_user_id, consent_given, consent_version,
                     behavior_tracking, profile_aggregation, ai_interventions,
                     cross_session_memory)
                VALUES (:tid, :uid, true, '1.0', true, true, true, true)
                ON CONFLICT (tenant_id, human_user_id) DO NOTHING
                """
            ).bindparams(tid=ta, uid=raw_uid)
        )
        await session.flush()

        # Attempt DELETE as tenant B — RLS must block it
        await session.execute(text(f"SET app.current_tenant = '{tb}'"))
        await session.execute(
            text("DELETE FROM user_twin_consent WHERE human_user_id = :uid").bindparams(uid=raw_uid)
        )
        await session.flush()

        # Switch back to tenant A and verify the record is still there
        await session.execute(text(f"SET app.current_tenant = '{ta}'"))
        result = await session.execute(
            text("SELECT COUNT(*) FROM user_twin_consent WHERE human_user_id = :uid").bindparams(
                uid=raw_uid
            )
        )
        count = result.scalar_one()
        assert count == 1, (
            f"Tenant B's DELETE erased {1 - count} consent record(s) owned by Tenant A — "
            "RLS must block cross-tenant DELETE"
        )
