"""Create canvas tables (canvases, canvas_blocks, canvas_connections,
canvas_collaborators, canvas_operations) and add RLS tenant isolation
on the canvases table.

Revision ID: 20260601_canvas_tables_with_rls
Revises: 20260530a
Create Date: 2026-06-01

Finding: CG-002 (L3 wiring audit 2026-06-01)
ADR: ADR-005 (tenant_id NOT NULL + RLS)

Note: RLS is applied only to the parent `canvases` table.
Child tables (canvas_blocks, canvas_connections, canvas_collaborators,
canvas_operations) are protected implicitly via FK JOIN through `canvases`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_canvas_tables_with_rls"
down_revision: str | Sequence[str] | None = "20260530a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline() -> bool:
    """Detect Alembic offline (--sql) mode to skip runtime-only DDL."""
    import sqlalchemy.engine.mock as mock_mod
    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Parent table: canvases                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "canvases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "template",
            sa.String(length=100),
            nullable=False,
            server_default="blank",
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_index("ix_canvases_tenant_id", "canvases", ["tenant_id"])
    op.create_index("ix_canvases_owner_id", "canvases", ["owner_id"])

    # ------------------------------------------------------------------ #
    # 2. canvas_blocks                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "canvas_blocks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column(
            "x", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0.00")
        ),
        sa.Column(
            "y", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0.00")
        ),
        sa.Column(
            "width",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("100.00"),
        ),
        sa.Column(
            "height",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("100.00"),
        ),
        sa.Column(
            "z_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_index("ix_canvas_blocks_canvas_id", "canvas_blocks", ["canvas_id"])
    op.create_index("ix_canvas_blocks_created_by", "canvas_blocks", ["created_by"])

    # ------------------------------------------------------------------ #
    # 3. canvas_connections                                                 #
    # ------------------------------------------------------------------ #
    op.create_table(
        "canvas_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_type",
            sa.String(length=50),
            nullable=False,
            server_default="straight",
        ),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "is_bidirectional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("trigger", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_canvas_connections_canvas_id", "canvas_connections", ["canvas_id"]
    )
    op.create_index(
        "ix_canvas_connections_from_block_id",
        "canvas_connections",
        ["from_block_id"],
    )
    op.create_index(
        "ix_canvas_connections_to_block_id", "canvas_connections", ["to_block_id"]
    )

    # ------------------------------------------------------------------ #
    # 4. canvas_collaborators                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "canvas_collaborators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index(
        "ix_canvas_collaborators_canvas_id",
        "canvas_collaborators",
        ["canvas_id"],
    )
    op.create_index(
        "ix_canvas_collaborators_user_id", "canvas_collaborators", ["user_id"]
    )
    op.create_index(
        "ix_canvas_collaborators_added_by", "canvas_collaborators", ["added_by"]
    )

    # ------------------------------------------------------------------ #
    # 5. canvas_operations                                                  #
    # ------------------------------------------------------------------ #
    op.create_table(
        "canvas_operations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "canvas_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canvases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index(
        "ix_canvas_operations_canvas_id", "canvas_operations", ["canvas_id"]
    )
    op.create_index(
        "ix_canvas_operations_target_id", "canvas_operations", ["target_id"]
    )
    op.create_index(
        "ix_canvas_operations_revision", "canvas_operations", ["revision"]
    )

    # ------------------------------------------------------------------ #
    # 6. RLS -- alleen op de parent `canvases` tabel (ADR-005)             #
    # ------------------------------------------------------------------ #
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text("ALTER TABLE canvases ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY canvas_tenant_isolation ON canvases "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )


def downgrade() -> None:
    # Drop RLS first, then tables (child tables first, parent last)
    if _is_postgresql() and not _is_offline():
        op.execute(
            sa.text("DROP POLICY IF EXISTS canvas_tenant_isolation ON canvases")
        )
        op.execute(sa.text("ALTER TABLE canvases DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_canvas_operations_revision", table_name="canvas_operations")
    op.drop_index("ix_canvas_operations_target_id", table_name="canvas_operations")
    op.drop_index("ix_canvas_operations_canvas_id", table_name="canvas_operations")
    op.drop_table("canvas_operations")

    op.drop_index("ix_canvas_collaborators_added_by", table_name="canvas_collaborators")
    op.drop_index("ix_canvas_collaborators_user_id", table_name="canvas_collaborators")
    op.drop_index("ix_canvas_collaborators_canvas_id", table_name="canvas_collaborators")
    op.drop_table("canvas_collaborators")

    op.drop_index("ix_canvas_connections_to_block_id", table_name="canvas_connections")
    op.drop_index("ix_canvas_connections_from_block_id", table_name="canvas_connections")
    op.drop_index("ix_canvas_connections_canvas_id", table_name="canvas_connections")
    op.drop_table("canvas_connections")

    op.drop_index("ix_canvas_blocks_created_by", table_name="canvas_blocks")
    op.drop_index("ix_canvas_blocks_canvas_id", table_name="canvas_blocks")
    op.drop_table("canvas_blocks")

    op.drop_index("ix_canvases_owner_id", table_name="canvases")
    op.drop_index("ix_canvases_tenant_id", table_name="canvases")
    op.drop_table("canvases")
