"""create tool_audit_logs table

Revision ID: 20260412_001_create_tool_audit_logs
Revises: 552d3cb43362
Create Date: 2026-04-12

Creates tool_audit_logs for ADR-015 (Tool Safety Allowlist) audit trail.

Each row records one tool invocation with:
- SHA-256 hash of the sanitized output (tamper detection)
- Per-tenant hash chain via previous_hash (ADR-019 compliant)
- tenant_id NOT NULL for strict isolation (ADR-005)

No offline mode guard needed: CREATE TABLE is always safe to emit.
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260412_001_create_tool_audit_logs"
down_revision: str | Sequence[str] | None = "552d3cb43362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tool_audit_logs table."""
    op.create_table(
        "tool_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Core identifiers (ADR-005: tenant_id NOT NULL)
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        # Tool details
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("tool_input", sa.JSON(), nullable=True),
        # Result
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        # Tamper evidence (ADR-019: SHA-256 hash chain)
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("audit_hash", sa.String(length=64), nullable=False),
        # HITL tracking
        sa.Column("hitl_ticket_ref", sa.String(length=50), nullable=True),
        sa.Column("hitl_approved_by", sa.String(length=100), nullable=True),
        # Timing
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Raw data for forensics (sanitized, no PII)
        sa.Column("tool_output", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes for tenant isolation and query performance
    op.create_index("ix_tool_audit_logs_tenant_id", "tool_audit_logs", ["tenant_id"])
    op.create_index("ix_tool_audit_logs_agent_id", "tool_audit_logs", ["agent_id"])
    op.create_index("ix_tool_audit_logs_task_id", "tool_audit_logs", ["task_id"])
    op.create_index("ix_tool_audit_logs_tool_name", "tool_audit_logs", ["tool_name"])
    op.create_index("ix_tool_audit_logs_hitl_ticket_ref", "tool_audit_logs", ["hitl_ticket_ref"])
    op.create_index("ix_tool_audit_logs_timestamp", "tool_audit_logs", ["timestamp"])


def downgrade() -> None:
    """Drop tool_audit_logs table."""
    op.drop_index("ix_tool_audit_logs_timestamp", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_hitl_ticket_ref", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_tool_name", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_task_id", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_agent_id", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_tenant_id", table_name="tool_audit_logs")
    op.drop_table("tool_audit_logs")
