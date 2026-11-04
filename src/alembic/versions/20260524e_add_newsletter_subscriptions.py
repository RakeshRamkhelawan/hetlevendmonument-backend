"""add_newsletter_subscriptions

Revision ID: 20260524e
Revises: 20260524d
Create Date: 2026-05-24 08:19:00

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260524e"
down_revision: str | Sequence[str] | None = "20260524d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["newsletter_subscriptions"]


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ("
            f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            f")"
        )
    )


def _disable_rls(table: str) -> None:
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def upgrade() -> None:
    op.create_table(
        "newsletter_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("confirm_token_hash", sa.String(length=128), nullable=True),
        sa.Column("unsubscribe_token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING_OPT_IN",
                "SUBSCRIBED",
                "UNSUBSCRIBED",
                "BOUNCED",
                name="newsletter_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_ip", sa.String(length=45), nullable=True),
        sa.Column("consent_user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("confirm_token_hash"),
        sa.UniqueConstraint("unsubscribe_token_hash"),
    )
    op.create_index(
        "idx_ns_tenant_email",
        "newsletter_subscriptions",
        ["tenant_id", "email"],
        unique=True,
    )
    op.create_index(
        "idx_ns_tenant_status",
        "newsletter_subscriptions",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_newsletter_subscriptions_tenant_id"),
        "newsletter_subscriptions",
        ["tenant_id"],
        unique=False,
    )

    if _is_postgresql():
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if _is_postgresql():
        for tbl in reversed(_RLS_TABLES):
            _disable_rls(tbl)

    op.drop_index(
        op.f("ix_newsletter_subscriptions_tenant_id"),
        table_name="newsletter_subscriptions",
    )
    op.drop_index("idx_ns_tenant_status", table_name="newsletter_subscriptions")
    op.drop_index("idx_ns_tenant_email", table_name="newsletter_subscriptions")
    op.drop_table("newsletter_subscriptions")
    op.execute("DROP TYPE IF EXISTS newsletter_status_enum")
