"""PostgreSQL integration tests for agentic_tasks RLS tenant isolation."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant, User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.multi_tenant,
]


async def _setup_rls(session: AsyncSession) -> None:
    """Enable RLS and create the tenant isolation policy for the test table."""
    await session.execute(text("ALTER TABLE agentic_tasks ENABLE ROW LEVEL SECURITY"))
    await session.execute(
        text("DROP POLICY IF EXISTS agentic_task_tenant_isolation ON agentic_tasks")
    )
    await session.execute(
        text(
            "CREATE POLICY agentic_task_tenant_isolation ON agentic_tasks "
            "FOR ALL USING ("
            "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            ")"
        )
    )
    await session.execute(text("ALTER TABLE agentic_tasks FORCE ROW LEVEL SECURITY"))


async def _seed_tenant_and_user(session: AsyncSession, suffix: str) -> dict[str, Any]:
    """Insert a tenant and a user via the ORM, returning their IDs."""
    tenant = Tenant(
        name=f"RLS Tenant {suffix}",
        slug=f"rls-tenant-{suffix}",
    )
    session.add(tenant)
    await session.flush()

    user = User(
        email=f"rls-user-{suffix}@example.com",
        hashed_password="x",
        tenant_id=tenant.id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.commit()

    return {"tenant_id": tenant.id, "user_id": user.id}


async def _insert_task(
    session: AsyncSession,
    task_id: str,
    tenant_id: int,
    title: str,
    user_id: int,
) -> None:
    await session.execute(
        text(
            "INSERT INTO agentic_tasks "
            "(id, tenant_id, title, status, priority, created_by, created_at, updated_at) "
            "VALUES (:id, :tenant_id, :title, 'pending', 'medium', :created_by, now(), now())"
        ),
        {
            "id": task_id,
            "tenant_id": tenant_id,
            "title": title,
            "created_by": user_id,
        },
    )
    await session.commit()


async def test_agentic_tasks_rls_tenant_a_cannot_see_tenant_b(
    postgres_session: AsyncSession,
) -> None:
    """RLS must hide tenant A's tasks from tenant B."""
    await _setup_rls(postgres_session)

    tenant_a = await _seed_tenant_and_user(postgres_session, "a")
    tenant_b = await _seed_tenant_and_user(postgres_session, "b")

    task_a = str(uuid.uuid4())
    task_b = str(uuid.uuid4())
    await _insert_task(
        postgres_session, task_a, tenant_a["tenant_id"], "Alpha", tenant_a["user_id"]
    )
    await _insert_task(postgres_session, task_b, tenant_b["tenant_id"], "Beta", tenant_b["user_id"])

    # Create an unprivileged role to ensure RLS is enforced.
    await postgres_session.execute(text("DROP ROLE IF EXISTS rls_task_test_user"))
    await postgres_session.execute(text("CREATE ROLE rls_task_test_user"))
    await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_task_test_user"))
    await postgres_session.execute(
        text("GRANT SELECT, INSERT ON agentic_tasks TO rls_task_test_user")
    )

    await postgres_session.execute(
        text(f"SET SESSION app.current_tenant = '{tenant_b['tenant_id']}'")
    )
    await postgres_session.execute(text("SET ROLE rls_task_test_user"))

    result = await postgres_session.execute(text("SELECT title FROM agentic_tasks"))
    names = {row[0] for row in result.fetchall()}

    await postgres_session.execute(text("RESET ROLE"))
    await postgres_session.execute(text("RESET app.current_tenant"))

    assert "Beta" in names, "Tenant B moet zijn eigen taak zien"
    assert "Alpha" not in names, "Tenant B mag NIET de taak van Tenant A zien"


async def test_agentic_tasks_create_requires_tenant_id(
    postgres_session: AsyncSession,
) -> None:
    """tenant_id is NOT NULL; inserts without it must fail."""
    await _setup_rls(postgres_session)

    tenant = await _seed_tenant_and_user(postgres_session, "null")

    with pytest.raises(IntegrityError):
        await postgres_session.execute(
            text(
                "INSERT INTO agentic_tasks "
                "(id, title, status, priority, created_by, created_at, updated_at) "
                "VALUES (:id, 'No Tenant', 'pending', 'medium', :created_by, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "created_by": tenant["user_id"]},
        )
        await postgres_session.commit()
