"""harden user_persona_preferences tenant integrity

Revision ID: 20260529b
Revises: 20260529a
Create Date: 2026-05-29 00:00:00.000000

Adds tenant_id and composite tenant-consistency constraints to user_persona_preferences.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260529b"
down_revision: str | None = "20260529a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rls_expr = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

    op.create_unique_constraint("uq_users_id_tenant", "users", ["id", "tenant_id"])
    op.create_unique_constraint("uq_personas_id_tenant", "personas", ["id", "tenant_id"])

    op.add_column("user_persona_preferences", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE user_persona_preferences AS upp
        SET tenant_id = u.tenant_id
        FROM users AS u
        WHERE upp.user_id = u.id
        """
    )
    op.alter_column("user_persona_preferences", "tenant_id", nullable=False)

    op.create_foreign_key(
        "fk_user_persona_preferences_tenant",
        "user_persona_preferences",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_user_persona_preferences_tenant_id",
        "user_persona_preferences",
        ["tenant_id"],
    )

    # IF EXISTS: constraint may not exist on fresh databases (only on existing dbs)
    op.execute(
        "ALTER TABLE user_persona_preferences DROP CONSTRAINT IF EXISTS uq_user_persona_preferences_user_id"
    )

    op.create_foreign_key(
        "fk_user_persona_preferences_user_tenant",
        "user_persona_preferences",
        "users",
        ["user_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_user_persona_preferences_persona_tenant",
        "user_persona_preferences",
        "personas",
        ["persona_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_persona_preferences_user_tenant",
        "user_persona_preferences",
        ["user_id", "tenant_id"],
    )

    op.execute("ALTER TABLE personas ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS personas_tenant_isolation ON personas")
    op.execute(
        f"CREATE POLICY personas_tenant_isolation ON personas USING (tenant_id = {rls_expr})"
    )

    op.execute("ALTER TABLE user_persona_preferences ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS user_persona_preferences_tenant_isolation ON user_persona_preferences"
    )
    op.execute(
        "CREATE POLICY user_persona_preferences_tenant_isolation "
        f"ON user_persona_preferences USING (tenant_id = {rls_expr})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS user_persona_preferences_tenant_isolation ON user_persona_preferences"
    )
    op.execute("DROP POLICY IF EXISTS personas_tenant_isolation ON personas")

    op.drop_constraint(
        "uq_user_persona_preferences_user_tenant",
        "user_persona_preferences",
        type_="unique",
    )
    op.drop_constraint(
        "fk_user_persona_preferences_persona_tenant",
        "user_persona_preferences",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_user_persona_preferences_user_tenant",
        "user_persona_preferences",
        type_="foreignkey",
    )
    op.create_unique_constraint(
        "uq_user_persona_preferences_user_id",
        "user_persona_preferences",
        ["user_id"],
    )

    op.drop_index("ix_user_persona_preferences_tenant_id", table_name="user_persona_preferences")
    op.drop_constraint(
        "fk_user_persona_preferences_tenant",
        "user_persona_preferences",
        type_="foreignkey",
    )
    op.drop_column("user_persona_preferences", "tenant_id")

    op.drop_constraint("uq_personas_id_tenant", "personas", type_="unique")
    op.drop_constraint("uq_users_id_tenant", "users", type_="unique")
