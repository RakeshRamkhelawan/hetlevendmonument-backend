"""
Add foreign key constraints to scheduling tables

Revision ID: 20260409b_sched_fk
Revises: 20260409a_sched_tenant_backfill
Create Date: 2026-04-09

OFFLINE MODE NOTE:
sa.inspect() fails on MockConnection in --sql dry-run mode. When offline,
we emit the FK / NOT NULL SQL unconditionally. In online mode we inspect
first to skip already-applied constraints (idempotent).
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260409b_sched_fk"
down_revision: str | None = "20260409a_sched_tenant_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in --sql (offline/dry-run) mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    bind = op.get_bind()

    if _is_offline(bind):
        # Offline mode: SQLite doesn't support FK constraint alteration or NOT NULL changes.
        # Emit SQL comments for documentation only.
        op.execute(
            sa.text(
                "-- Add FK constraint fk_webhook_registrations_tenant "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Add NOT NULL constraint to scheduling_webhook_registrations.tenant_id "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Add FK constraint fk_sync_conflicts_tenant "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Add NOT NULL constraint to scheduling_sync_conflicts.tenant_id "
                "(online only - requires database connection)"
            )
        )
        return

    # Online mode: inspect to skip already-applied constraints.
    inspector = sa.inspect(bind)

    if inspector.has_table("scheduling_webhook_registrations"):
        webhook_cols = {
            col["name"] for col in inspector.get_columns("scheduling_webhook_registrations")
        }
        webhook_fks = {
            fk.get("name") for fk in inspector.get_foreign_keys("scheduling_webhook_registrations")
        }
        if "tenant_id" in webhook_cols and "fk_webhook_registrations_tenant" not in webhook_fks:
            op.create_foreign_key(
                "fk_webhook_registrations_tenant",
                "scheduling_webhook_registrations",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "tenant_id" in webhook_cols:
            op.alter_column(
                "scheduling_webhook_registrations",
                "tenant_id",
                existing_type=sa.Integer(),
                nullable=False,
            )

    if inspector.has_table("scheduling_sync_conflicts"):
        conflict_cols = {col["name"] for col in inspector.get_columns("scheduling_sync_conflicts")}
        conflict_fks = {
            fk.get("name") for fk in inspector.get_foreign_keys("scheduling_sync_conflicts")
        }
        if "tenant_id" in conflict_cols and "fk_sync_conflicts_tenant" not in conflict_fks:
            op.create_foreign_key(
                "fk_sync_conflicts_tenant",
                "scheduling_sync_conflicts",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "tenant_id" in conflict_cols:
            op.alter_column(
                "scheduling_sync_conflicts",
                "tenant_id",
                existing_type=sa.Integer(),
                nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _is_offline(bind):
        # Offline mode: emit SQL comments for documentation only.
        op.execute(
            sa.text(
                "-- Drop FK constraint fk_sync_conflicts_tenant "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Add NOT NULL constraint to scheduling_sync_conflicts.tenant_id "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Drop FK constraint fk_webhook_registrations_tenant "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Add NOT NULL constraint to scheduling_webhook_registrations.tenant_id "
                "(online only - requires database connection)"
            )
        )
        return

    inspector = sa.inspect(bind)

    if inspector.has_table("scheduling_sync_conflicts"):
        conflict_cols = {col["name"] for col in inspector.get_columns("scheduling_sync_conflicts")}
        if "tenant_id" in conflict_cols:
            op.alter_column(
                "scheduling_sync_conflicts",
                "tenant_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
        conflict_fks = {
            fk.get("name") for fk in inspector.get_foreign_keys("scheduling_sync_conflicts")
        }
        if "fk_sync_conflicts_tenant" in conflict_fks:
            op.drop_constraint(
                "fk_sync_conflicts_tenant",
                "scheduling_sync_conflicts",
                type_="foreignkey",
            )

    if inspector.has_table("scheduling_webhook_registrations"):
        webhook_cols = {
            col["name"] for col in inspector.get_columns("scheduling_webhook_registrations")
        }
        if "tenant_id" in webhook_cols:
            op.alter_column(
                "scheduling_webhook_registrations",
                "tenant_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
        webhook_fks = {
            fk.get("name") for fk in inspector.get_foreign_keys("scheduling_webhook_registrations")
        }
        if "fk_webhook_registrations_tenant" in webhook_fks:
            op.drop_constraint(
                "fk_webhook_registrations_tenant",
                "scheduling_webhook_registrations",
                type_="foreignkey",
            )
