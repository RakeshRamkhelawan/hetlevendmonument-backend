"""Add extra_metadata to collective_knowledge.

Revision ID: 20260509_140000
Revises: 20260506_add_unified_agent_fields
Create Date: 2026-05-09 14:00:00
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260509_140000"
down_revision: str | None = "20260506_add_unified_agent_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(conn: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t)"
        ),
        {"t": table_name},
    )
    return bool(result.scalar())


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("ALTER TABLE collective_knowledge ADD COLUMN IF NOT EXISTS extra_metadata JSON")
        return
    conn = op.get_bind()
    if _is_offline(conn):
        op.execute("ALTER TABLE collective_knowledge ADD COLUMN IF NOT EXISTS extra_metadata JSON")
        return

    if not _table_exists(conn, "collective_knowledge"):
        # Table missing on fresh databases (created via archived migration on prod).
        # Create it here so subsequent migrations can rely on its existence.
        op.create_table(
            "collective_knowledge",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("knowledge_type", sa.String(), nullable=False, index=True),
            sa.Column("content_hash", sa.String(64), nullable=False, index=True),
            sa.Column("content", postgresql.JSONB(), nullable=False),
            sa.Column("embedding", sa.LargeBinary(), nullable=True),
            sa.Column("embedding_model", sa.String(), nullable=True),
            sa.Column("source_agent", sa.String(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("access_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
            sa.Column("extra_metadata", sa.JSON(), nullable=True),
        )
    else:
        # Table exists (production path) - only add the new column.
        op.execute("ALTER TABLE collective_knowledge ADD COLUMN IF NOT EXISTS extra_metadata JSON")


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute("ALTER TABLE collective_knowledge DROP COLUMN IF EXISTS extra_metadata")
        return
    conn = op.get_bind()
    if _is_offline(conn):
        op.execute("ALTER TABLE collective_knowledge DROP COLUMN IF EXISTS extra_metadata")
        return

    if _table_exists(conn, "collective_knowledge"):
        op.execute("ALTER TABLE collective_knowledge DROP COLUMN IF EXISTS extra_metadata")
