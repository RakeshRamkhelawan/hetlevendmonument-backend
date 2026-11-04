# tests/integration/test_billing_migration.py
import pytest
from sqlalchemy import text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_existing_tenants_have_default_subscription_tier(db_session):
    await db_session.execute(
        text(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb, data_residency) "
            "VALUES ('Raw SQL Tenant', 'raw-sql-tenant', true, 10, 50, 5, 'global')"
        )
    )
    await db_session.commit()

    result = await db_session.execute(
        text(
            "SELECT subscription_tier, subscription_status FROM tenants WHERE slug = 'raw-sql-tenant'"
        )
    )
    row = result.fetchone()

    assert row is not None
    assert row[0] == "free"
    assert row[1] == "active"
