import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.multi_tenant]


async def test_canvas_rls_tenant_a_cannot_see_tenant_b(postgres_session: AsyncSession) -> None:
    """
    CG-002: Tenant A mag de canvas van Tenant B NIET zien via RLS.

    Scenario:
    - Tenant 1 maakt canvas "Alpha" aan
    - Tenant 2 maakt canvas "Beta" aan
    - RLS context: app.current_tenant = '2'
    - Query op canvases retourneert ALLEEN "Beta" -- NIET "Alpha"
    """
    canvas_id_a = uuid.uuid4()
    canvas_id_b = uuid.uuid4()

    # Apply RLS policy manually for the test since Base.metadata.create_all() bypasses Alembic
    await postgres_session.execute(text("ALTER TABLE canvases ENABLE ROW LEVEL SECURITY"))
    await postgres_session.execute(
        text("DROP POLICY IF EXISTS canvas_tenant_isolation ON canvases")
    )
    await postgres_session.execute(
        text(
            "CREATE POLICY canvas_tenant_isolation ON canvases "
            "FOR ALL USING ("
            "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            ")"
        )
    )
    # RLS policies bypass the owner of the table (usually postgres superuser) 
    # so we must switch to a non-superuser or FORCE RLS
    await postgres_session.execute(text("ALTER TABLE canvases FORCE ROW LEVEL SECURITY"))

    # Insert direct (bypass RLS via superuser session die BYPASSRLS heeft)
    await postgres_session.execute(
        text(
            "INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version, created_at, updated_at) "
            "VALUES (:id, 1, :owner, 'Alpha', 'blank', false, 1, now(), now())"
        ),
        {"id": str(canvas_id_a), "owner": str(uuid.uuid4())},
    )
    await postgres_session.execute(
        text(
            "INSERT INTO canvases (id, tenant_id, owner_id, name, template, is_public, version, created_at, updated_at) "
            "VALUES (:id, 2, :owner, 'Beta', 'blank', false, 1, now(), now())"
        ),
        {"id": str(canvas_id_b), "owner": str(uuid.uuid4())},
    )
    await postgres_session.commit()

    # RLS policies bypass superusers. Create a temporary unprivileged role to test RLS properly
    await postgres_session.execute(text("DROP ROLE IF EXISTS rls_test_user"))
    await postgres_session.execute(text("CREATE ROLE rls_test_user"))
    await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_test_user"))
    await postgres_session.execute(text("GRANT SELECT, INSERT ON canvases TO rls_test_user"))

    # Stel RLS-context in op Tenant 2 en switch naar unprivileged role
    await postgres_session.execute(text("SET SESSION app.current_tenant = '2'"))
    await postgres_session.execute(text("SET ROLE rls_test_user"))

    result = await postgres_session.execute(text("SELECT name FROM canvases"))
    names = {row[0] for row in result.fetchall()}

    # Reset role en session variable
    await postgres_session.execute(text("RESET ROLE"))
    await postgres_session.execute(text("RESET app.current_tenant"))

    assert "Beta" in names, "Tenant 2 moet zijn eigen canvas zien"
    assert "Alpha" not in names, "Tenant 2 mag NIET de canvas van Tenant 1 zien (RLS breach)"


async def test_canvas_create_requires_tenant_id(postgres_session: AsyncSession) -> None:
    """tenant_id kan niet NULL zijn -- INSERT zonder tenant_id faalt met IntegrityError."""
    with pytest.raises(IntegrityError):
        await postgres_session.execute(
            text(
                "INSERT INTO canvases (id, owner_id, name, template, is_public, version, created_at, updated_at) "
                "VALUES (:id, :owner, 'No Tenant', 'blank', false, 1, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
        )
        await postgres_session.commit()
