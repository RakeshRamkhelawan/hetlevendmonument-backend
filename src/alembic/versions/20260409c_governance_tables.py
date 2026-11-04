"""Add governance agent tables (EU AI Act Phase 1-4).

Creates five governance tables required by EU AI Act Articles 9, 15, 17, 72:
  - governance_alerts            (Art. 15: alert management)
  - governance_accuracy_metrics  (Art. 15: accuracy tracking)
  - governance_risk_entries      (Art. 9:  risk register)
  - governance_quality_checks    (Art. 17: quality gate)
  - governance_authority_reports (Art. 72: authority reporting)

Revision ID: 20260409c_governance_tables
Revises: 20260409b_sched_fk
Create Date: 2026-04-09

Note: The file alembic/versions/governance_agent_tables.py (old root path)
contains an equivalent migration but with down_revision = "merge_local_fix",
which does not exist in the active chain (src/alembic/versions/). That
migration was never reachable. This file is the canonical replacement.
"""

from __future__ import annotations

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260409c_governance_tables"
down_revision: str | None = "20260409b_sched_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- governance_alerts -----------------------------------------------------
    op.create_table(
        "governance_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("violation_type", sa.String(100), nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("occurrence_count", sa.Integer, default=1),
        sa.Column("details", postgresql.JSONB, default=dict),
        sa.Column("acknowledged", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_governance_alerts_tenant_id", "governance_alerts", ["tenant_id"])
    op.create_index("ix_governance_alerts_dedup_key", "governance_alerts", ["dedup_key"])

    # -- governance_accuracy_metrics -------------------------------------------
    # NOTE: success is Integer (0/1), NOT Boolean -- matches ORM in accuracy_monitor.py (C-6 fix)
    op.create_table(
        "governance_accuracy_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("success", sa.Integer, nullable=False),  # 1 = success, 0 = failure
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_governance_accuracy_metrics_tenant_id",
        "governance_accuracy_metrics",
        ["tenant_id"],
    )
    op.create_index(
        "ix_governance_accuracy_metrics_agent_name",
        "governance_accuracy_metrics",
        ["agent_name"],
    )
    op.create_index(
        "ix_governance_accuracy_metrics_recorded_at",
        "governance_accuracy_metrics",
        ["recorded_at"],
    )

    # -- governance_risk_entries -----------------------------------------------
    op.create_table(
        "governance_risk_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("risk_description", sa.Text, nullable=False, server_default=""),
        sa.Column("likelihood", sa.String(30), nullable=False),
        sa.Column("impact", sa.String(30), nullable=False),
        sa.Column("mitigation", sa.Text, nullable=False, server_default=""),
        sa.Column("residual_risk", sa.String(50), nullable=False),
        sa.Column("last_reviewed", sa.DateTime, nullable=True),
        sa.Column("reviewer_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_governance_risk_entries_tenant_id",
        "governance_risk_entries",
        ["tenant_id"],
    )

    # -- governance_quality_checks ---------------------------------------------
    op.create_table(
        "governance_quality_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("check_type", sa.String(50), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("details", postgresql.JSONB, default=dict),
        sa.Column("checked_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("checked_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_governance_quality_checks_tenant_id",
        "governance_quality_checks",
        ["tenant_id"],
    )

    # -- governance_authority_reports ------------------------------------------
    op.create_table(
        "governance_authority_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("authority_name", sa.String(200), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_governance_authority_reports_tenant_id",
        "governance_authority_reports",
        ["tenant_id"],
    )


def downgrade() -> None:
    # Drop in reverse creation order (dependency order)
    op.drop_index("ix_governance_authority_reports_tenant_id", "governance_authority_reports")
    op.drop_table("governance_authority_reports")

    op.drop_index("ix_governance_quality_checks_tenant_id", "governance_quality_checks")
    op.drop_table("governance_quality_checks")

    op.drop_index("ix_governance_risk_entries_tenant_id", "governance_risk_entries")
    op.drop_table("governance_risk_entries")

    op.drop_index("ix_governance_accuracy_metrics_recorded_at", "governance_accuracy_metrics")
    op.drop_index("ix_governance_accuracy_metrics_agent_name", "governance_accuracy_metrics")
    op.drop_index("ix_governance_accuracy_metrics_tenant_id", "governance_accuracy_metrics")
    op.drop_table("governance_accuracy_metrics")

    op.drop_index("ix_governance_alerts_dedup_key", "governance_alerts")
    op.drop_index("ix_governance_alerts_tenant_id", "governance_alerts")
    op.drop_table("governance_alerts")
