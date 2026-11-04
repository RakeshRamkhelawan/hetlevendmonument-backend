"""add agent_critiques table for CritiqueStore PostgreSQL persistence

Revision ID: e4f5c648cf94
Revises: 20260618_add_focus_builder_tables
Create Date: 2026-06-19

SP-AGT-005: CritiqueStore -> PostgreSQL persistentie
- Maakt agent_critiques tabel aan voor CriticAgent kwaliteitsbeoordelingen
- Indexes op critique_id (unique), tenant_id, agent_name, created_at
- RLS policy voor tenant-isolatie (ADR-005)
- Idempotent: safe te herdraaien als tabel al bestaat
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4f5c648cf94"
down_revision: Union[str, Sequence[str], None] = "20260618_add_focus_builder_tables"
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

    if "agent_critiques" not in existing:
        op.create_table(
            "agent_critiques",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("critique_id", sa.String(length=255), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=False),
            sa.Column("task_id", sa.String(length=255), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column(
                "issues",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "suggestions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("critique_id"),
        )
        op.create_index("ix_agent_critiques_critique_id", "agent_critiques", ["critique_id"])
        op.create_index("ix_agent_critiques_tenant_id", "agent_critiques", ["tenant_id"])
        op.create_index("ix_agent_critiques_agent_name", "agent_critiques", ["agent_name"])
        op.create_index("ix_agent_critiques_task_id", "agent_critiques", ["task_id"])
        op.create_index("ix_agent_critiques_created_at", "agent_critiques", ["created_at"])

        op.execute("ALTER TABLE agent_critiques ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation_policy ON agent_critiques
            FOR ALL
            USING (
                tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
            );
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON agent_critiques;")
    op.execute("DROP TABLE IF EXISTS agent_critiques;")
