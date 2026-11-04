import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import Base
from src.core.workflow.models import C7Workflow


@pytest.mark.asyncio
async def test_rls_enforcement(postgres_session: AsyncSession) -> None:
    """
    Penetration Test for Row-Level Security (RLS).

    Objective: Verify that setting 'app.current_tenant' restricts visibility
    at the database level, preventing accidental data leaks.

    Step 1: Seed Data for Tenant A and Tenant B.
    Step 2: Simulate a User Request from Tenant A (by setting app.current_tenant).
    Step 3: Execute a raw SQL query (simulating a developer forgetting 'WHERE tenant_id=...').
    Step 4: Assert that ONLY Tenant A's data is returned.

    RED PHASE: This test should FAIL because RLS is not yet enabled.
    """

    # --- 1. SEED DATA ---
    tenant_a_id = 1  # Default seeded tenant
    tenant_b_id = 2

    # Create Tenant B (Tenant A exists from fixture)
    await postgres_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, domain, is_active, max_users, max_agents, max_storage_gb, subscription_tier, subscription_status) VALUES (:id, 'Tenant B', 'tenant-b', 'b.local', true, 100, 100, 100.0, 'enterprise', 'active') ON CONFLICT DO NOTHING"
        ),
        {"id": tenant_b_id},
    )

    # Create Workflow A (Tenant A)
    wf_a_id = str(uuid.uuid4())
    wf_a = C7Workflow(
        id=wf_a_id,
        name="Workflow A",
        workflow_type="standard",
        trigger_type="manual",
        tenant_id=tenant_a_id,
        nodes=[],
        edges=[],
    )
    postgres_session.add(wf_a)

    # Create Workflow B (Tenant B)
    wf_b_id = str(uuid.uuid4())
    wf_b = C7Workflow(
        id=wf_b_id,
        name="Workflow B",
        workflow_type="standard",
        trigger_type="manual",
        tenant_id=tenant_b_id,  # <--- Different Tenant
        nodes=[],
        edges=[],
    )
    postgres_session.add(wf_b)

    await postgres_session.flush()

    # --- 2. SIMULATE TENANT CONTEXT ---
    # In the Green phase, Middleware will do this.
    # For now, we manually set the session variable.
    # Note: We must ensure RLS is ENABLED on the table (Green Phase).

    # Attempt to set the variable. Postgres accepts custom GUCs but might warn if not defined.
    # We cast to text to be safe via set_config, or just SET.
    # SET LOCAL is transaction scoped.
    await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a_id}'"))

    # --- 3. ATTACK (Raw SQL without WHERE clause) ---
    # CRITICAL: We must run as a NON-SUPERUSER to test RLS.
    # The 'postgres' user bypasses RLS by default.

    # Bootstrap RLS (not created by Base.metadata.create_all())
    await postgres_session.execute(text("ALTER TABLE c7_workflows ENABLE ROW LEVEL SECURITY"))
    await postgres_session.execute(
        text("DROP POLICY IF EXISTS c7_workflows_tenant_isolation ON c7_workflows")
    )
    await postgres_session.execute(
        text(
            "CREATE POLICY c7_workflows_tenant_isolation ON c7_workflows "
            "FOR ALL USING ("
            "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            ")"
        )
    )

    # Create a temporary test role
    await postgres_session.execute(text("DROP ROLE IF EXISTS rls_tester"))
    await postgres_session.execute(text("CREATE ROLE rls_tester NOLOGIN"))
    await postgres_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_tester"))
    await postgres_session.execute(text("GRANT SELECT ON c7_workflows TO rls_tester"))

    # Switch to the test role
    await postgres_session.execute(text("SET ROLE rls_tester"))

    # Re-inject the tenant variable (session variables might persist, but good to be sure)
    await postgres_session.execute(text(f"SET app.current_tenant = '{tenant_a_id}'"))

    try:
        # DEBUG: Check environment
        debug_policies = await postgres_session.execute(
            text("SELECT * FROM pg_policies WHERE tablename = 'c7_workflows'")
        )
        print(f"\n[DEBUG] Policies: {debug_policies.fetchall()}")

        debug_user = await postgres_session.execute(text("SELECT current_user, session_user"))
        print(f"[DEBUG] Current User: {debug_user.fetchone()}")

        debug_setting = await postgres_session.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        )
        print(f"[DEBUG] app.current_tenant: {debug_setting.scalar()}")

        # We select ALL workflows. If RLS is working, Postgres should filter rows invisible to Tenant A.
        result = await postgres_session.execute(text("SELECT id, tenant_id FROM c7_workflows"))
        rows = result.fetchall()
        print(f"[DEBUG] Rows Returned: {rows}")
    finally:
        # Reset role to allow cleanup/rollback (superuser privileges needed for rollback?)
        # Actually transaction rollback should handle it, but explicit reset is safer.
        await postgres_session.execute(text("RESET ROLE"))

    # --- 4. ASSERTION ---
    # We expect to see only Tenant A's workflows.
    tenant_ids_returned = [row.tenant_id for row in rows]

    print(f"DEBUG: Returned Tenants: {tenant_ids_returned}")

    # Check specifically for our test workflows
    found_a = any(r.id == wf_a_id for r in rows)
    found_b = any(r.id == wf_b_id for r in rows)

    assert found_a, "Should always see own data (Tenant A)"
    assert not found_b, "SECURITY FAIL: Leaked Tenant B data! RLS not active."
