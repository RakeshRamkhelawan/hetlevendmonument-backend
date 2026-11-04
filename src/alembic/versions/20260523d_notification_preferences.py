"""Notification preferences with RLS

Revision ID: 20260523d_notification_preferences
Revises: 20260523c_add_rls_c7_workflow_tables
Create Date: 2026-05-23 16:10:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260523d_notification_preferences"
down_revision = "20260523c_add_rls_c7_workflow_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CLAUDE.md regel 14: safe execution check for offline mode compatibility
    bind = op.get_bind()
    is_offline = isinstance(bind, sa.engine.mock.MockConnection)

    op.create_table(
        "user_notification_preferences",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "daily_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("25"),
        ),
        sa.Column(
            "delivery_mode",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'individual'"),
        ),
        sa.Column(
            "critical_always_immediate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("quiet_hours_start", sa.SmallInteger(), nullable=True),
        sa.Column("quiet_hours_end", sa.SmallInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "daily_limit BETWEEN 0 AND 100",
            name="chk_notif_daily_limit_range",
        ),
        sa.CheckConstraint(
            "delivery_mode IN ('individual','batched','digest')",
            name="chk_notif_delivery_mode",
        ),
        sa.CheckConstraint(
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) "
            "OR (quiet_hours_start BETWEEN 0 AND 23 "
            "AND quiet_hours_end BETWEEN 0 AND 23)",
            name="chk_notif_quiet_hours_range",
        ),
    )
    op.create_index(
        "idx_notif_prefs_tenant",
        "user_notification_preferences",
        ["tenant_id"],
    )

    # RLS per ADR-005 + ADR-027 S.7
    if is_offline:
        op.execute(sa.text("-- ALTER TABLE user_notification_preferences ENABLE ROW LEVEL SECURITY;"))
        op.execute(
            sa.text(
                "-- CREATE POLICY tenant_iso_notif_prefs ON user_notification_preferences "
                "-- USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::integer);"
            )
        )
    else:
        op.execute("ALTER TABLE user_notification_preferences ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_iso_notif_prefs ON user_notification_preferences
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::integer);
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_offline = isinstance(bind, sa.engine.mock.MockConnection)

    if is_offline:
        op.execute(sa.text("-- DROP POLICY IF EXISTS tenant_iso_notif_prefs ON user_notification_preferences;"))
    else:
        op.execute("DROP POLICY IF EXISTS tenant_iso_notif_prefs ON user_notification_preferences;")
        
    op.drop_index("idx_notif_prefs_tenant")
    op.drop_table("user_notification_preferences")
