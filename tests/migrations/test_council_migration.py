"""
Integration tests for Council migrations.
"""

import pytest
import sqlalchemy as sa

@pytest.mark.integration
@pytest.mark.asyncio
async def test_council_migration_upgrade_creates_tables(db_session):
    """Verifieer dat na migratie de tabellen bestaan."""
    result = await db_session.execute(sa.text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name IN ('council_decisions', 'officer_verdicts')"
    ))
    tables = {row[0] for row in result}
    assert "council_decisions" in tables
    assert "officer_verdicts" in tables

@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_council_rls_policy_enforces_tenant_isolation(db_session, setup_test_tenants):
    """Tenant A kan geen decisions van tenant B inserten zonder context-switch."""
    # Assuming setup_test_tenants returns a list or tuple of created tenant ids
    tenant_a, tenant_b = setup_test_tenants[0], setup_test_tenants[1]
    
    # Set context to tenant A
    await db_session.execute(sa.text(f"SET app.current_tenant = '{tenant_a}'"))
    
    # Using an anonymous block to test RLS
    await db_session.execute(sa.text(f"""
        INSERT INTO council_decisions (decision_id, proposal_id, tenant_id, user_id, timestamp, verdict, action_type, action_params, data_classification, model_id, model_version, reasoning, explanation_for_user, deliberation_ms, decision_hash)
        VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', {tenant_a}, 1, now(), 'approved', 'nav', '{{}}', 'internal', 'gpt', '4', 'res', 'exp', 10, 'hash1');
    """))
    await db_session.commit()

    # Query as tenant A should see the record
    await db_session.execute(sa.text(f"SET app.current_tenant = '{tenant_a}'"))
    res_a = (await db_session.execute(sa.text("SELECT * FROM council_decisions"))).fetchall()
    assert len(res_a) == 1

    # Query as tenant B should not see the record
    await db_session.execute(sa.text(f"SET app.current_tenant = '{tenant_b}'"))
    res_b = (await db_session.execute(sa.text("SELECT * FROM council_decisions"))).fetchall()
    assert len(res_b) == 0
