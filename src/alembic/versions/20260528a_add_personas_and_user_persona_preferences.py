"""add personas and user_persona_preferences

Revision ID: 20260528a
Revises: 20260525c
Create Date: 2026-05-28

"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260528a"
down_revision = "20260525c"
branch_labels = None
depends_on = None

_PERSONA_CATEGORY = sa.Enum(
    "technical",
    "creative",
    "analytical",
    "supportive",
    "expert",
    "custom",
    name="personacategory",
)


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    bind = op.get_bind()
    if _is_offline(bind):
        existing = set()
    else:
        inspector = sa.inspect(bind)
        existing = set(inspector.get_table_names())

    if "personas" not in existing:
        # op.create_table emits CREATE TYPE personacategory exactly once here.
        # Do NOT call _PERSONA_CATEGORY.create() before this -- it would cause a
        # double-CREATE (once explicit, once from op.create_table DDL generator).
        op.create_table(
            "personas",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("avatar_url", sa.String(500), nullable=True),
            sa.Column(
                "category",
                _PERSONA_CATEGORY,
                nullable=False,
                server_default="custom",
            ),
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("temperature", sa.String(10), nullable=True, server_default="0.7"),
            sa.Column("verbosity", sa.String(20), nullable=True, server_default="balanced"),
            sa.Column("tone", sa.String(50), nullable=True, server_default="professional"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_personas_tenant_id", "personas", ["tenant_id"])

    if "user_persona_preferences" not in existing:
        op.create_table(
            "user_persona_preferences",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("persona_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_user_persona_preferences_user_id"),
        )
        op.create_index(
            "ix_user_persona_preferences_user_id", "user_persona_preferences", ["user_id"]
        )


def downgrade() -> None:
    op.drop_index("ix_user_persona_preferences_user_id", table_name="user_persona_preferences")
    op.drop_table("user_persona_preferences")
    op.drop_index("ix_personas_tenant_id", table_name="personas")
    op.drop_table("personas")
    _PERSONA_CATEGORY.drop(op.get_bind(), checkfirst=True)
