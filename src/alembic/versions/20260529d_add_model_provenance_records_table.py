"""add model_provenance_records table

EU AI Act Article 53 -- model provenance tracking with tamper-evident hashes.
6-month retention minimum (retention_until column). Soft-delete only.

Revision ID: 20260529d
Revises: 20260529c
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260529d"
down_revision = "20260529c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_provenance_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_provenance_tenant_registered",
        "model_provenance_records",
        ["tenant_id", "registered_at"],
    )
    op.create_index(
        "ix_provenance_tenant_id",
        "model_provenance_records",
        ["tenant_id"],
    )

    op.execute(sa.text("ALTER TABLE model_provenance_records ENABLE ROW LEVEL SECURITY;"))
    op.execute(
        sa.text(
            "CREATE POLICY tenant_isolation ON model_provenance_records "
            "USING (tenant_id = current_setting('app.current_tenant', TRUE)::integer);"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON model_provenance_records;"))
    op.drop_index("ix_provenance_tenant_id", table_name="model_provenance_records")
    op.drop_index("ix_provenance_tenant_registered", table_name="model_provenance_records")
    op.drop_table("model_provenance_records")
