"""
Add tenant_id to scheduling_webhook_registrations and scheduling_sync_conflicts

Revision ID: 20260409_sched_tenant
Revises: 20260408b_activepieces_tzaware
Create Date: 2026-04-09

OFFLINE MODE NOTE:
sa.inspect() fails on MockConnection in --sql dry-run mode. When offline,
we emit the ADD COLUMN / CREATE INDEX SQL unconditionally. The statements
are idempotent on a fresh DB (column does not yet exist) and safe to review.
In online mode we inspect first to skip already-applied changes.
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260409_sched_tenant"
down_revision: str | None = "20260408b_activepieces_tzaware"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in --sql (offline/dry-run) mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    bind = op.get_bind()

    if _is_offline(bind):
        # Offline mode: emit SQL unconditionally for review/dry-run.
        op.add_column(
            "scheduling_webhook_registrations",
            sa.Column("tenant_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_webhook_registrations_tenant_id",
            "scheduling_webhook_registrations",
            ["tenant_id"],
        )
        op.add_column(
            "scheduling_sync_conflicts",
            sa.Column("tenant_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_sync_conflicts_tenant_id",
            "scheduling_sync_conflicts",
            ["tenant_id"],
        )
        return

    # Online mode: inspect to skip already-applied changes.
    inspector = sa.inspect(bind)

    if inspector.has_table("scheduling_webhook_registrations"):
        webhook_cols = {
            col["name"] for col in inspector.get_columns("scheduling_webhook_registrations")
        }
        if "tenant_id" not in webhook_cols:
            op.add_column(
                "scheduling_webhook_registrations",
                sa.Column("tenant_id", sa.Integer(), nullable=True),
            )

        webhook_indexes = {
            idx["name"] for idx in inspector.get_indexes("scheduling_webhook_registrations")
        }
        if "ix_webhook_registrations_tenant_id" not in webhook_indexes:
            op.create_index(
                "ix_webhook_registrations_tenant_id",
                "scheduling_webhook_registrations",
                ["tenant_id"],
            )

    if inspector.has_table("scheduling_sync_conflicts"):
        conflict_cols = {col["name"] for col in inspector.get_columns("scheduling_sync_conflicts")}
        if "tenant_id" not in conflict_cols:
            op.add_column(
                "scheduling_sync_conflicts",
                sa.Column("tenant_id", sa.Integer(), nullable=True),
            )

        conflict_indexes = {
            idx["name"] for idx in inspector.get_indexes("scheduling_sync_conflicts")
        }
        if "ix_sync_conflicts_tenant_id" not in conflict_indexes:
            op.create_index(
                "ix_sync_conflicts_tenant_id",
                "scheduling_sync_conflicts",
                ["tenant_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _is_offline(bind):
        op.drop_index("ix_sync_conflicts_tenant_id", table_name="scheduling_sync_conflicts")
        op.drop_column("scheduling_sync_conflicts", "tenant_id")
        op.drop_index(
            "ix_webhook_registrations_tenant_id",
            table_name="scheduling_webhook_registrations",
        )
        op.drop_column("scheduling_webhook_registrations", "tenant_id")
        return

    inspector = sa.inspect(bind)

    if inspector.has_table("scheduling_sync_conflicts"):
        conflict_indexes = {
            idx["name"] for idx in inspector.get_indexes("scheduling_sync_conflicts")
        }
        if "ix_sync_conflicts_tenant_id" in conflict_indexes:
            op.drop_index("ix_sync_conflicts_tenant_id", table_name="scheduling_sync_conflicts")
        conflict_cols = {col["name"] for col in inspector.get_columns("scheduling_sync_conflicts")}
        if "tenant_id" in conflict_cols:
            op.drop_column("scheduling_sync_conflicts", "tenant_id")

    if inspector.has_table("scheduling_webhook_registrations"):
        webhook_indexes = {
            idx["name"] for idx in inspector.get_indexes("scheduling_webhook_registrations")
        }
        if "ix_webhook_registrations_tenant_id" in webhook_indexes:
            op.drop_index(
                "ix_webhook_registrations_tenant_id",
                table_name="scheduling_webhook_registrations",
            )
        webhook_cols = {
            col["name"] for col in inspector.get_columns("scheduling_webhook_registrations")
        }
        if "tenant_id" in webhook_cols:
            op.drop_column("scheduling_webhook_registrations", "tenant_id")
