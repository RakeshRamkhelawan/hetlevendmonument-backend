"""add_request_audit_logs

Revision ID: 3ee55ea8e623
Revises: 20260601b_add_feature_flags_and_rls
Create Date: 2026-06-01 20:30:04.167706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ee55ea8e623'
down_revision: Union[str, Sequence[str], None] = '20260601b_add_feature_flags_and_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    conn = op.get_bind()
    return conn.dialect.name == "postgresql"


def _is_offline(bind) -> bool:
    return isinstance(bind, sa.engine.mock.MockConnection)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if _is_offline(bind):
        return False
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    """Upgrade schema."""
    if not _table_exists("request_audit_logs"):
        op.create_table(
            "request_audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("user_email", sa.String(length=255), nullable=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=True),
            sa.Column("method", sa.String(length=10), nullable=False),
            sa.Column("path", sa.String(length=500), nullable=False),
            sa.Column("query_params", sa.Text(), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("response_time_ms", sa.Integer(), nullable=True),
            sa.Column("ip_address", sa.String(length=50), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=True),
            sa.Column("resource_type", sa.String(length=100), nullable=True),
            sa.Column("resource_id", sa.String(length=100), nullable=True),
            sa.Column("changes", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id")
        )
        op.create_index(
            "ix_request_audit_logs_request_id",
            "request_audit_logs",
            ["request_id"],
            unique=False
        )
        op.create_index(
            "ix_request_audit_logs_timestamp",
            "request_audit_logs",
            ["timestamp"],
            unique=False
        )
        op.create_index(
            "ix_request_audit_logs_user_id",
            "request_audit_logs",
            ["user_id"],
            unique=False
        )
        op.create_index(
            "ix_request_audit_logs_tenant_id",
            "request_audit_logs",
            ["tenant_id"],
            unique=False
        )

    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE request_audit_logs ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON request_audit_logs"))
        op.execute(
            sa.text(
                "CREATE POLICY tenant_isolation ON request_audit_logs "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')"
                ")"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    if _is_postgresql():
        op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON request_audit_logs"))
        op.execute(sa.text("ALTER TABLE request_audit_logs DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_request_audit_logs_tenant_id", table_name="request_audit_logs")
    op.drop_index("ix_request_audit_logs_user_id", table_name="request_audit_logs")
    op.drop_index("ix_request_audit_logs_timestamp", table_name="request_audit_logs")
    op.drop_index("ix_request_audit_logs_request_id", table_name="request_audit_logs")
    op.drop_table("request_audit_logs")
