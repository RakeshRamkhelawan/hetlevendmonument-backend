"""Add compound index on c7_execution_tasks(status, created_at) for stale-task query

Revision ID: 20260522b_stale_task_index
Revises: 20260522_add_rls_core_tables
Create Date: 2026-05-22

Supports the hourly stale-task-cleanup actor (ADR-007: 1-hour timeout).
Query: WHERE status IN (PENDING, RUNNING) AND created_at < NOW() - 1h
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260522b_stale_task_index"
down_revision: str | Sequence[str] | None = "20260522_add_rls_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def _create_c7_tables_if_missing(conn: sa.engine.Connection) -> None:
    """Create the C7 workflow tables on fresh databases.

    On production these tables were created by the archived 0001_baseline_schema
    migration. Fresh databases never ran that archive, so we create them here
    with IF NOT EXISTS guards.
    """
    if _is_offline(conn):
        existing: set[str] = set()
    else:
        inspector = sa.inspect(conn)
        existing = set(inspector.get_table_names())

    # ENUM types (idempotent via DO block)
    conn.execute(
        sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflow_status_enum') THEN
                CREATE TYPE workflow_status_enum AS ENUM
                    ('pending','running','succeeded','failed','cancelled','timeout');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status_enum') THEN
                CREATE TYPE task_status_enum AS ENUM
                    ('pending','running','succeeded','failed','retrying','timeout','skipped');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type_enum') THEN
                CREATE TYPE event_type_enum AS ENUM
                    ('workflow_created','workflow_started','workflow_completed','workflow_failed',
                     'workflow_cancelled','task_started','task_completed','task_failed',
                     'task_retrying','task_timeout','status_changed');
            END IF;
        END $$;
    """)
    )

    if "c7_workflows" not in existing:
        op.create_table(
            "c7_workflows",
            sa.Column("id", sa.String(50), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=True, default=1),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("workflow_type", sa.String(50), nullable=False),
            sa.Column("trigger_type", sa.String(50), nullable=False),
            sa.Column("trigger_config", sa.JSON(), nullable=True),
            sa.Column("nodes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("edges", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("variables", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("clock_timestamp()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "c7_workflow_executions" not in existing:
        op.create_table(
            "c7_workflow_executions",
            sa.Column("id", sa.String(50), primary_key=True, index=True),
            sa.Column("execution_id", sa.String(100), unique=True, nullable=False, index=True),
            sa.Column(
                "workflow_id",
                sa.String(50),
                sa.ForeignKey("c7_workflows.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "status", sa.String(50), nullable=False, server_default="pending", index=True
            ),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("initiated_by", sa.String(100), nullable=True),
            sa.Column("correlation_id", sa.String(100), nullable=True, index=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tasks_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tasks_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("input_json", sa.JSON(), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=True),
            sa.Column("results_json", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("clock_timestamp()"),
                nullable=False,
            ),
        )

    if "c7_execution_tasks" not in existing:
        op.create_table(
            "c7_execution_tasks",
            sa.Column("id", sa.String(50), primary_key=True, index=True),
            sa.Column(
                "execution_id",
                sa.String(50),
                sa.ForeignKey("c7_workflow_executions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("task_ref", sa.String(100), nullable=False),
            sa.Column("task_type", sa.String(100), nullable=False),
            sa.Column(
                "status", sa.String(50), nullable=False, server_default="pending", index=True
            ),
            sa.Column("worker_id", sa.String(100), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("error_json", sa.JSON(), nullable=True),
            sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("clock_timestamp()"),
                nullable=False,
            ),
            sa.UniqueConstraint("execution_id", "task_ref", name="uq_c7_execution_task"),
        )

    if "c7_execution_events" not in existing:
        op.create_table(
            "c7_execution_events",
            sa.Column("id", sa.String(50), primary_key=True, index=True),
            sa.Column(
                "execution_id",
                sa.String(50),
                sa.ForeignKey("c7_workflow_executions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("event_type", sa.String(50), nullable=False, index=True),
            sa.Column("task_ref", sa.String(100), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("clock_timestamp()"),
                nullable=False,
                index=True,
            ),
        )


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_c7_execution_task_status_created "
            "ON c7_execution_tasks (status, created_at)"
        )
        return
    conn = op.get_bind()
    _create_c7_tables_if_missing(conn)
    # CREATE INDEX IF NOT EXISTS is safe on both fresh and existing databases
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_c7_execution_task_status_created "
            "ON c7_execution_tasks (status, created_at)"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "idx_c7_execution_task_status_created",
        table_name="c7_execution_tasks",
    )
