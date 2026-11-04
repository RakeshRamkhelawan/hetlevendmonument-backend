"""extend_documents_table

Revision ID: 47ca3df1f5e6
Revises: 11ffd3a57d26
Create Date: 2026-05-28 20:49:09.086634

"""

from typing import Union
from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "47ca3df1f5e6"
down_revision: str | Sequence[str] | None = "11ffd3a57d26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if _is_offline(bind):
        documents_exists = False
    else:
        inspector = sa.inspect(bind)
        documents_exists = inspector.has_table("documents")

    if not documents_exists:
        # Table missing on fresh databases (was created by archived migration on prod).
        # Create it here with the full post-extend schema so subsequent migrations work.
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "uploaded_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("filename", sa.String(512), nullable=False),
            sa.Column("mime_type", sa.String(127), nullable=True),
            sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("storage_backend", sa.String(20), nullable=False, server_default="local"),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("checksum_sha256", sa.String(64), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("clock_timestamp()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"], unique=False)
        op.create_index("ix_documents_status", "documents", ["status"], unique=False)
        op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"], unique=False)
        op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"], unique=False)
        op.create_index("ix_documents_mime_type", "documents", ["mime_type"], unique=False)
    else:
        # Table exists (production path) - add new columns with IF NOT EXISTS.
        op.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'pending'"
        )
        op.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
        )
        op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content JSONB")
        op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        op.execute("CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_documents_status ON documents (status)")
        op.execute("UPDATE documents SET deleted_at = clock_timestamp() WHERE is_deleted = true")

    # Enable RLS (idempotent via DROP ... IF EXISTS before CREATE)
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON documents")
    op.execute(
        "CREATE POLICY tenant_isolation_policy ON documents FOR ALL "
        "USING (tenant_id = current_setting('app.current_tenant')::int)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Restore is_deleted from deleted_at
    op.execute("UPDATE documents SET is_deleted = true WHERE deleted_at IS NOT NULL")

    # Drop RLS
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON documents")
    op.execute("ALTER TABLE documents DISABLE ROW LEVEL SECURITY")

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "content")
    op.drop_column("documents", "version")
    op.drop_column("documents", "status")
    # ### end Alembic commands ###
