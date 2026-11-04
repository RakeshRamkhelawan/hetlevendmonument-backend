"""council_tables

Revision ID: 20260523a_council
Revises: 20260522c_enforce_sub
Create Date: 2026-05-23 15:00:00.000000
"""

from typing import Union
from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "20260523a_council"
down_revision: str | Sequence[str] | None = "20260522c_enforce_sub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    # council_decisions tabel
    op.create_table(
        "council_decisions",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("action_type", sa.String(128), nullable=False),
        sa.Column("action_params", postgresql.JSONB, nullable=False),
        sa.Column("data_classification", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("explanation_for_user", sa.Text(), nullable=False),
        sa.Column("deliberation_ms", sa.Integer(), nullable=False),
        sa.Column("hitl_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("modifications", postgresql.JSONB, nullable=True),
        sa.Column("decision_hash", sa.String(64), nullable=False),
        sa.Column("previous_decision_hash", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("idx_council_tenant_time", "council_decisions", ["tenant_id", "timestamp"])
    op.create_index("idx_council_user_time", "council_decisions", ["tenant_id", "user_id", "timestamp"])
    op.create_index("idx_council_verdict", "council_decisions", ["tenant_id", "verdict"])

    # officer_verdicts tabel
    op.create_table(
        "officer_verdicts",
        sa.Column("verdict_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("officer_name", sa.String(64), nullable=False),
        sa.Column("officer_version", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("deliberation_ms", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("used_cache", sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(["decision_id"], ["council_decisions.decision_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("idx_officer_dec_id", "officer_verdicts", ["decision_id"])

    bind = op.get_bind()
    if not isinstance(bind, sa.engine.mock.MockConnection):
        # RLS per ADR-005
        op.execute("ALTER TABLE council_decisions ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_council ON council_decisions
            USING (tenant_id = current_setting('app.current_tenant')::integer);
        """)
        op.execute("ALTER TABLE officer_verdicts ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_officer_verdicts ON officer_verdicts
            USING (tenant_id = current_setting('app.current_tenant')::integer);
        """)

def downgrade() -> None:
    bind = op.get_bind()
    if not isinstance(bind, sa.engine.mock.MockConnection):
        op.execute("DROP POLICY IF EXISTS tenant_isolation_officer_verdicts ON officer_verdicts;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_council ON council_decisions;")

    op.drop_index("idx_officer_dec_id", table_name="officer_verdicts")
    op.drop_table("officer_verdicts")

    op.drop_index("idx_council_verdict", table_name="council_decisions")
    op.drop_index("idx_council_user_time", table_name="council_decisions")
    op.drop_index("idx_council_tenant_time", table_name="council_decisions")
    op.drop_table("council_decisions")
