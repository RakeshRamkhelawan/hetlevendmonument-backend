"""Backfill tenant_id in scheduling tables.

Revision ID: 20260409a_sched_tenant_backfill
Revises: 20260409_sched_tenant
Create Date: 2026-04-09

OFFLINE MODE NOTE:
This migration executes UPDATE statements (data migration). It cannot run
meaningfully in --sql dry-run mode against a MockConnection. When offline,
it emits a SQL comment so the dry-run chain compiles without error.
In online mode it performs the full backfill and fails explicitly if any
NULL tenant_id rows remain.
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260409a_sched_tenant_backfill"
down_revision: str | None = "20260409_sched_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in --sql (offline/dry-run) mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def _table_has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def _count_null_tenant_rows(connection: sa.Connection, table_name: str) -> int:
    result = connection.execute(
        sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
    )
    return int(result.scalar() or 0)


def upgrade() -> None:
    connection = op.get_bind()

    if _is_offline(connection):
        # Data migrations cannot run against a MockConnection.
        # Emit a no-op comment so the offline chain compiles successfully.
        op.execute(sa.text("-- backfill: scheduling tenant_id (online only)"))
        return

    inspector = sa.inspect(connection)

    integrations_ready = _table_has_column(
        inspector,
        "scheduling_calendar_integrations",
        "tenant_id",
    )

    webhook_ready = _table_has_column(
        inspector,
        "scheduling_webhook_registrations",
        "tenant_id",
    ) and _table_has_column(inspector, "scheduling_webhook_registrations", "integration_id")

    conflicts_ready = _table_has_column(
        inspector,
        "scheduling_sync_conflicts",
        "tenant_id",
    ) and _table_has_column(inspector, "scheduling_sync_conflicts", "integration_id")

    if integrations_ready and webhook_ready:
        connection.execute(
            sa.text(
                """
                UPDATE scheduling_webhook_registrations w
                SET tenant_id = i.tenant_id
                FROM scheduling_calendar_integrations i
                WHERE w.integration_id = i.id
                  AND w.tenant_id IS NULL
                """
            )
        )

    if integrations_ready and conflicts_ready:
        connection.execute(
            sa.text(
                """
                UPDATE scheduling_sync_conflicts c
                SET tenant_id = i.tenant_id
                FROM scheduling_calendar_integrations i
                WHERE c.integration_id = i.id
                  AND c.tenant_id IS NULL
                """
            )
        )

    if webhook_ready:
        webhook_nulls = _count_null_tenant_rows(connection, "scheduling_webhook_registrations")
        if webhook_nulls > 0:
            raise RuntimeError(
                "Backfill failed for scheduling_webhook_registrations: "
                f"{webhook_nulls} rows still have tenant_id IS NULL"
            )

    if conflicts_ready:
        conflict_nulls = _count_null_tenant_rows(connection, "scheduling_sync_conflicts")
        if conflict_nulls > 0:
            raise RuntimeError(
                "Backfill failed for scheduling_sync_conflicts: "
                f"{conflict_nulls} rows still have tenant_id IS NULL"
            )


def downgrade() -> None:
    """No-op downgrade.

    This migration only backfills data. Column contract is handled in a separate
    migration and should be reversed there if needed.
    """
    return
