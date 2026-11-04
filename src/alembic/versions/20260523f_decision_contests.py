"""Create decision_contests table for GDPR art. 22 contestations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260523f_decision_contests"
down_revision = "20260523e_ai_act_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_contests",
        sa.Column(
            "contest_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason_category", sa.String(64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("resolution_text", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolver_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["council_decisions.decision_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.CheckConstraint(
            "status IN ('pending','reviewing','upheld','overturned','withdrawn')",
            name="chk_contest_status",
        ),
    )
    op.create_index(
        "idx_contest_tenant_status",
        "decision_contests",
        ["tenant_id", "status"],
    )
    op.create_index(
        "idx_contest_decision",
        "decision_contests",
        ["decision_id"],
    )
    op.execute("ALTER TABLE decision_contests ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_iso_contests ON decision_contests
        USING (
            tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_iso_contests ON decision_contests;")
    op.execute("DROP INDEX IF EXISTS idx_contest_decision;")
    op.execute("DROP INDEX IF EXISTS idx_contest_tenant_status;")
    op.execute("DROP TABLE IF EXISTS decision_contests;")
