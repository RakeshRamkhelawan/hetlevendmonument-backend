"""DATA-001/002, DB-AUDIT-001/002 -- agentic-domain tenant isolation
(Sprint Dag 1 Groep 4, AUDIT-ARCH-2026-07-02).

Standard isolation test pattern (backend-patterns.md #11), mirroring
tests/integration/test_canvas_tenant_isolation.py: tenant A must not see tenant B's
rows, and tenant_id must be enforced NOT NULL at the DB level. RLS policies bypass the
table owner/superuser by default -- since integration tests connect as postgres
(the table owner), a temporary unprivileged role + FORCE ROW LEVEL SECURITY is used to
actually exercise the policy, matching the existing canvas isolation test's approach.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.multi_tenant]


async def test_prompt_templates_rls_tenant_a_cannot_see_tenant_b(
    postgres_session: AsyncSession,
) -> None:
    """Tenant A mag de prompt_templates van Tenant B NIET zien via RLS."""
    # Apply RLS policy manually for the test since Base.metadata.create_all() bypasses
    # Alembic (matches test_canvas_tenant_isolation.py's approach) -- migration 884d744f6aa9
    # applies the same statements for real deploys.
    await postgres_session.execute(text("ALTER TABLE prompt_templates ENABLE ROW LEVEL SECURITY"))
    await postgres_session.execute(
        text("DROP POLICY IF EXISTS prompt_templates_tenant_isolation ON prompt_templates")
    )
    await postgres_session.execute(
        text(
            "CREATE POLICY prompt_templates_tenant_isolation ON prompt_templates USING ("
            "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            ")"
        )
    )
    # RLS policies bypass the table owner (postgres superuser in this fixture).
    await postgres_session.execute(text("ALTER TABLE prompt_templates FORCE ROW LEVEL SECURITY"))

    await postgres_session.execute(
        text(
            "INSERT INTO prompt_templates (name, version, system_prompt, tenant_id) "
            "VALUES ('alpha-template', '1.0', 'prompt for tenant 1', 1)"
        )
    )
    await postgres_session.execute(
        text(
            "INSERT INTO prompt_templates (name, version, system_prompt, tenant_id) "
            "VALUES ('beta-template', '1.0', 'prompt for tenant 2', 2)"
        )
    )
    await postgres_session.commit()

    await postgres_session.execute(text("DROP ROLE IF EXISTS agentic_rls_test_user"))
    await postgres_session.execute(text("CREATE ROLE agentic_rls_test_user"))
    await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO agentic_rls_test_user"))
    await postgres_session.execute(
        text("GRANT SELECT, INSERT ON prompt_templates TO agentic_rls_test_user")
    )

    await postgres_session.execute(text("SET SESSION app.current_tenant = '2'"))
    await postgres_session.execute(text("SET ROLE agentic_rls_test_user"))

    result = await postgres_session.execute(text("SELECT name FROM prompt_templates"))
    names = {row[0] for row in result.fetchall()}

    await postgres_session.execute(text("RESET ROLE"))
    await postgres_session.execute(text("RESET app.current_tenant"))

    assert "beta-template" in names, "Tenant 2 moet zijn eigen prompt_template zien"
    assert "alpha-template" not in names, (
        "Tenant 2 mag NIET het prompt_template van Tenant 1 zien (RLS breach)"
    )


async def test_features_rls_tenant_a_cannot_see_tenant_b(
    postgres_session: AsyncSession,
) -> None:
    """Tenant A mag de features van Tenant B NIET zien via RLS."""
    await postgres_session.execute(text("ALTER TABLE features ENABLE ROW LEVEL SECURITY"))
    await postgres_session.execute(
        text("DROP POLICY IF EXISTS features_tenant_isolation ON features")
    )
    await postgres_session.execute(
        text(
            "CREATE POLICY features_tenant_isolation ON features USING ("
            "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            ")"
        )
    )
    await postgres_session.execute(text("ALTER TABLE features FORCE ROW LEVEL SECURITY"))

    feature_id_a = f"feature-a-{uuid.uuid4().hex[:8]}"
    feature_id_b = f"feature-b-{uuid.uuid4().hex[:8]}"

    await postgres_session.execute(
        text(
            "INSERT INTO features (id, name, description, category, tenant_id) "
            "VALUES (:id, 'Alpha Feature', 'desc', 'workflow', 1)"
        ),
        {"id": feature_id_a},
    )
    await postgres_session.execute(
        text(
            "INSERT INTO features (id, name, description, category, tenant_id) "
            "VALUES (:id, 'Beta Feature', 'desc', 'workflow', 2)"
        ),
        {"id": feature_id_b},
    )
    await postgres_session.commit()

    await postgres_session.execute(text("DROP ROLE IF EXISTS agentic_rls_test_user"))
    await postgres_session.execute(text("CREATE ROLE agentic_rls_test_user"))
    await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO agentic_rls_test_user"))
    await postgres_session.execute(
        text("GRANT SELECT, INSERT ON features TO agentic_rls_test_user")
    )

    await postgres_session.execute(text("SET SESSION app.current_tenant = '2'"))
    await postgres_session.execute(text("SET ROLE agentic_rls_test_user"))

    result = await postgres_session.execute(text("SELECT name FROM features"))
    names = {row[0] for row in result.fetchall()}

    await postgres_session.execute(text("RESET ROLE"))
    await postgres_session.execute(text("RESET app.current_tenant"))

    assert "Beta Feature" in names, "Tenant 2 moet zijn eigen feature zien"
    assert "Alpha Feature" not in names, (
        "Tenant 2 mag NIET de feature van Tenant 1 zien (RLS breach)"
    )


async def test_prompt_templates_requires_tenant_id(postgres_session: AsyncSession) -> None:
    """tenant_id kan niet NULL zijn -- INSERT zonder tenant_id faalt met IntegrityError."""
    with pytest.raises(IntegrityError):
        await postgres_session.execute(
            text(
                "INSERT INTO prompt_templates (name, version, system_prompt) "
                "VALUES ('no-tenant-template', '1.0', 'prompt with no tenant')"
            )
        )
        await postgres_session.commit()


async def test_features_requires_tenant_id(postgres_session: AsyncSession) -> None:
    """tenant_id kan niet NULL zijn -- INSERT zonder tenant_id faalt met IntegrityError."""
    with pytest.raises(IntegrityError):
        await postgres_session.execute(
            text(
                "INSERT INTO features (id, name, description, category) "
                "VALUES (:id, 'No Tenant Feature', 'desc', 'workflow')"
            ),
            {"id": f"no-tenant-{uuid.uuid4().hex[:8]}"},
        )
        await postgres_session.commit()
