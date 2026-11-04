"""
Integration tests for User Notification Preferences Migration.
"""

import pytest
from sqlalchemy import text

from src.core.copilot.notification.models import NotificationPreferences
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo


@pytest.mark.integration
async def test_preferences_table_exists_after_migration(db_session):
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'user_notification_preferences'"
        )
    )
    assert result.scalar_one_or_none() == "user_notification_preferences"


@pytest.mark.integration
@pytest.mark.security
async def test_rls_isolates_tenants_on_preferences(db_session):
    # Setup test data
    # Create two tenants
    await db_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, is_active, subscription_tier, max_users, max_agents, max_storage_gb) VALUES (901, 'Test Tenant 1', 'test1', true, 'free', 10, 5, 5) ON CONFLICT DO NOTHING"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, is_active, subscription_tier, max_users, max_agents, max_storage_gb) VALUES (902, 'Test Tenant 2', 'test2', true, 'free', 10, 5, 5) ON CONFLICT DO NOTHING"
        )
    )

    # Create two users
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, tenant_id, is_active) VALUES (901, 'user901@test.com', 'hash', 901, true) ON CONFLICT DO NOTHING"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, tenant_id, is_active) VALUES (902, 'user902@test.com', 'hash', 902, true) ON CONFLICT DO NOTHING"
        )
    )

    # Base.metadata.create_all does not run Alembic migrations.
    # We must manually enable RLS and create the policy for this test.
    await db_session.execute(text("ALTER TABLE user_notification_preferences ENABLE ROW LEVEL SECURITY"))
    await db_session.execute(text("DROP POLICY IF EXISTS tenant_iso_notif_prefs ON user_notification_preferences"))
    await db_session.execute(
        text(
            "CREATE POLICY tenant_iso_notif_prefs ON user_notification_preferences "
            "USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::integer)"
        )
    )

    repo = UserNotificationPreferencesRepo(db_session)

    # Set app.current_tenant to 901
    await db_session.execute(text("SET LOCAL app.current_tenant = '901'"))

    # Insert preference for user 901
    await repo.upsert(NotificationPreferences(user_id=901, tenant_id=901, daily_limit=10))

    # User 901 can see their preference
    result1 = await db_session.execute(
        text("SELECT user_id FROM user_notification_preferences WHERE user_id = 901")
    )
    assert result1.scalar_one_or_none() == 901

    # CRITICAL: We must run as a NON-SUPERUSER to test RLS.
    await db_session.execute(text("DROP ROLE IF EXISTS rls_tester"))
    await db_session.execute(text("CREATE ROLE rls_tester NOLOGIN"))
    await db_session.execute(text("GRANT USAGE ON SCHEMA public TO rls_tester"))
    await db_session.execute(text("GRANT SELECT ON user_notification_preferences TO rls_tester"))
    
    # Switch to the test role
    await db_session.execute(text("SET ROLE rls_tester"))
    
    # Set app.current_tenant to 902 AFTER switching roles
    await db_session.execute(text("SET LOCAL app.current_tenant = '902'"))
    
    try:
        # Tenant 902 cannot see user 901's preference due to RLS
        result2 = await db_session.execute(
            text("SELECT user_id FROM user_notification_preferences WHERE user_id = 901")
        )
        assert result2.scalar_one_or_none() is None
    finally:
        await db_session.execute(text("RESET ROLE"))

    # Cleanup
    await db_session.execute(text("SET LOCAL app.current_tenant = '901'"))
    await db_session.execute(
        text("DELETE FROM user_notification_preferences WHERE user_id IN (901, 902)")
    )
    await db_session.execute(text("DELETE FROM users WHERE id IN (901, 902)"))
    await db_session.execute(text("DELETE FROM tenants WHERE id IN (901, 902)"))
    await db_session.commit()
