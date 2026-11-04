"""Company Layer - Create pack activation audit log table

Revision ID: 20260311_005_create_pack_activation_audit_log
Revises: 20260311_004_create_company_template_tables
Create Date: 2026-03-11

Creates the pack_activation_audit_logs table for Golden Rule R2:
No pack activation without explainable match -- every activation MUST
be audited with match_reason, confidence, and score breakdown.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "20260311_005_create_pack_activation_audit_log"
down_revision = "20260311_004_create_company_template_tables"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # =========================================================================
    # PACK ACTIVATION AUDIT LOG TABLE
    # =========================================================================
    op.create_table(  # noqa: create-table
        "pack_activation_audit_logs",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Tenant and company references
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Pack details
        sa.Column("pack_id", sa.String(100), nullable=False, index=True),
        sa.Column("pack_name", sa.String(200), nullable=False),
        # Scoring
        sa.Column("score", sa.Float, nullable=False),
        sa.Column(
            "confidence",
            sa.String(20),
            nullable=False,
            comment="EXACT, HIGH, MEDIUM, LOW, or NONE",
        ),
        sa.Column(
            "match_reason",
            sa.Text,
            nullable=False,
            comment="Human-readable explanation of the match (Golden Rule R2)",
        ),
        # Detailed breakdown (JSONB for flexibility)
        sa.Column(
            "input_signals",
            postgresql.JSONB,
            server_default="{}",
            comment="Input signals used for scoring (dept name, type, sector, etc.)",
        ),
        sa.Column(
            "score_breakdown",
            postgresql.JSONB,
            server_default="{}",
            comment="Detailed score breakdown by signal type",
        ),
        # Activation details
        sa.Column(
            "activated_automatically",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="True if auto-activated (score >= 0.70), False if suggested or manual",
        ),
        # User confirmation (for manual activations)
        sa.Column(
            "user_confirmed",
            sa.Boolean,
            nullable=True,
            comment="Null for auto-activation, True/False for user decision",
        ),
        sa.Column(
            "confirmed_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # =========================================================================
    # INDEXES FOR QUERY PERFORMANCE
    # =========================================================================

    # Tenant isolation queries
    op.create_index(
        "idx_audit_tenant_company",
        "pack_activation_audit_logs",
        ["tenant_id", "company_id"],
    )

    # Pack lookup queries
    op.create_index("idx_audit_pack", "pack_activation_audit_logs", ["pack_id"])

    # Time-based queries (recent activations)
    op.create_index(
        "idx_audit_created",
        "pack_activation_audit_logs",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )

    # Department lookup
    op.create_index(
        "idx_audit_department", "pack_activation_audit_logs", ["department_id"]
    )

    # Confidence-based queries
    op.create_index(
        "idx_audit_confidence", "pack_activation_audit_logs", ["confidence"]
    )

    # Auto-activation queries
    op.create_index(
        "idx_audit_auto_activated",
        "pack_activation_audit_logs",
        ["activated_automatically", "created_at"],
    )

    # =========================================================================
    # POSTGRESQL-SPECIFIC: RLS + COMMENTS
    # =========================================================================
    if _is_postgresql():
        op.execute("ALTER TABLE pack_activation_audit_logs ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY pack_activation_audit_tenant_isolation ON pack_activation_audit_logs
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )

        op.execute(
            """
            COMMENT ON TABLE pack_activation_audit_logs IS
            'Audit trail for domain pack activations. Golden Rule R2: No activation without explainable match.'
        """
        )


def downgrade() -> None:
    # Drop table and all associated objects (indexes, policies)
    op.drop_table("pack_activation_audit_logs")
