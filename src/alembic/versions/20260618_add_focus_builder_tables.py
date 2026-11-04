"""add focus builder flows and pieces cache tables

Revision ID: 20260618_add_focus_builder_tables
Revises: 20260605a
Create Date: 2026-06-18

SP-FB-001: FocusBuilder P0-fixes
- Creates the canonical `flows` table (src/domains/flows/models.py).
- Creates the legacy `focus_builder_flows` table (src/core/focus_builder/models.py)
  so that legacy code and seed scripts do not hit schema drift in production.
- Creates the global `focus_builder_pieces_cache` table.
- Adds RLS policies on tenant-scoped tables for tenant isolation (ADR-005).

All CREATE statements are conditional so the migration is safe to re-run
against databases that already have the tables (e.g. local test fixtures).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260618_add_focus_builder_tables"
down_revision: Union[str, Sequence[str], None] = "20260605a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if _is_offline(bind):
        existing: set[str] = set()
    else:
        inspector = sa.inspect(bind)
        existing = set(inspector.get_table_names())

    if "flows" not in existing:
        op.create_table(
            "flows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "react_flow_graph",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("ui_version", sa.String(length=20), nullable=True, server_default="1.0"),
            sa.Column("activepieces_flow_id", sa.String(length=255), nullable=True),
            sa.Column("activepieces_project_id", sa.String(length=255), nullable=True),
            sa.Column(
                "activepieces_version", sa.Integer(), nullable=True, server_default=sa.text("1")
            ),
            sa.Column(
                "activepieces_flow_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("is_published", sa.Boolean(), nullable=True, server_default=sa.text("false")),
            sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("execution_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_flows_activepieces_flow_id", "flows", ["activepieces_flow_id"])
        op.create_index("ix_flows_created_by", "flows", ["created_by"])
        op.create_index("ix_flows_name", "flows", ["name"])
        op.create_index("ix_flows_tenant_id", "flows", ["tenant_id"])
        op.create_index("ix_flows_updated_at", "flows", ["updated_at"])

        # Tenant isolation (ADR-005): NULLIF avoids "unrecognized configuration parameter"
        # when app.current_tenant is not set inside a connection.
        op.execute("ALTER TABLE flows ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation_policy ON flows
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer);
            """
        )

    if "focus_builder_flows" not in existing:
        op.create_table(
            "focus_builder_flows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=2000), nullable=True),
            sa.Column(
                "react_flow_graph",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("activepieces_flow_id", sa.String(length=255), nullable=True),
            sa.Column("activepieces_project_id", sa.String(length=255), nullable=True),
            sa.Column(
                "activepieces_version", sa.Integer(), nullable=True, server_default=sa.text("1")
            ),
            sa.Column("is_published", sa.Boolean(), nullable=True, server_default=sa.text("false")),
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("activepieces_flow_id"),
        )
        op.create_index(
            "ix_focus_builder_flows_activepieces_flow_id",
            "focus_builder_flows",
            ["activepieces_flow_id"],
        )
        op.create_index(
            "ix_focus_builder_flows_is_published",
            "focus_builder_flows",
            ["is_published"],
        )
        op.create_index(
            "ix_focus_builder_flows_tenant_id",
            "focus_builder_flows",
            ["tenant_id"],
        )

        # Tenant isolation for legacy table as well (ADR-005).
        op.execute("ALTER TABLE focus_builder_flows ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation_policy_fb_flows ON focus_builder_flows
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer);
            """
        )

    if "focus_builder_pieces_cache" not in existing:
        op.create_table(
            "focus_builder_pieces_cache",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("piece_name", sa.String(length=255), nullable=False),
            sa.Column("piece_version", sa.String(length=50), nullable=True),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("logo_url", sa.String(length=500), nullable=True),
            sa.Column(
                "actions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "triggers",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "auth_config",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "last_synced_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("piece_name"),
        )
        op.create_index(
            "ix_focus_builder_pieces_cache_piece_name",
            "focus_builder_pieces_cache",
            ["piece_name"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_fb_flows ON focus_builder_flows;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON flows;")
    op.execute("DROP TABLE IF EXISTS focus_builder_pieces_cache;")
    op.execute("DROP TABLE IF EXISTS focus_builder_flows;")
    op.execute("DROP TABLE IF EXISTS flows;")
