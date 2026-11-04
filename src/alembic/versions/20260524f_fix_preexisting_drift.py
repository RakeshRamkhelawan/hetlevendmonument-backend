"""Fix pre-existing drift: create 4 missing tables.

Revision ID: 20260524f
Revises: 20260524e
Create Date: 2026-05-24 10:00:00.000000

This migration creates four tables that exist in SQLAlchemy models but were
never added to the active migration chain (their original migrations were
moved to archive/):

- company_analytics_opt_out
- pack_usage_aggregates
- benchmarking_query_logs
- two_factor_auth

No existing tables or columns are altered -- zero data risk.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524f"
down_revision: str | Sequence[str] | None = "20260524e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    conn = op.get_bind()
    return conn.dialect.name == "postgresql"


def _is_offline(bind) -> bool:
    """Detect Alembic offline mode (CI dry-run with --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def _table_exists(table_name: str) -> bool:
    """Return True if table already exists in the current schema.

    Returns False in offline mode (so SQL is emitted unconditionally for
    review). CLAUDE.md regel 14: never call sa.inspect on MockConnection.
    """
    bind = op.get_bind()
    if _is_offline(bind):
        return False
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    if not _is_postgresql():
        return

    if not _table_exists("pack_usage_aggregates"):
        _create_pack_usage_aggregates()

    if not _table_exists("company_analytics_opt_out"):
        _create_company_analytics_opt_out()

    if not _table_exists("benchmarking_query_logs"):
        _create_benchmarking_query_logs()

    if not _table_exists("two_factor_auth"):
        _create_two_factor_auth()


def _create_pack_usage_aggregates() -> None:
    """Create pack_usage_aggregates with current PackUsageAggregate model schema."""
    op.create_table(  # noqa: create-table
        "pack_usage_aggregates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "date",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "sector",
            sa.String(length=100),
            nullable=False,
            index=True,
            comment="Industry sector for grouping",
        ),
        sa.Column(
            "company_type",
            sa.String(length=20),
            nullable=False,
            index=True,
            comment="mkb, zzp, or enterprise",
        ),
        sa.Column(
            "employee_bucket",
            sa.String(length=20),
            nullable=False,
            index=True,
            comment="Employee count bucket: 1-9, 10-49, 50-249, 250+",
        ),
        sa.Column(
            "pack_id",
            sa.String(length=100),
            nullable=False,
            index=True,
            comment="Domain pack identifier",
        ),
        sa.Column(
            "pack_name",
            sa.String(length=200),
            nullable=True,
            comment="Human-readable pack name",
        ),
        sa.Column(
            "total_companies",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Total companies in this sector/bucket (k-anonymity check)",
        ),
        sa.Column(
            "active_companies",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Number of companies actively using this pack",
        ),
        sa.Column(
            "total_activations",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Cumulative total pack activations",
        ),
        sa.Column(
            "daily_activations",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="New activations on this specific date",
        ),
        sa.Column(
            "adoption_rate_pct",
            sa.Float(),
            nullable=False,
            default=0.0,
            comment="Percentage of companies using this pack (0-100)",
        ),
        sa.Column(
            "avg_usage_per_company",
            sa.Float(),
            nullable=False,
            default=0.0,
            comment="Average usage events per active company",
        ),
        sa.Column(
            "k_anonymity_met",
            sa.Boolean(),
            nullable=False,
            default=True,
            comment="Whether k-anonymity (>=5 companies) is satisfied",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Index("idx_pack_usage_sector_date", "sector", "date"),
        sa.Index("idx_pack_usage_pack_date", "pack_id", "date"),
        sa.Index("idx_pack_usage_type_sector", "company_type", "sector"),
        sa.Index("idx_pack_usage_k_anon", "k_anonymity_met", "total_companies"),
        sa.Index(
            "idx_pack_usage_unique",
            "date",
            "sector",
            "company_type",
            "employee_bucket",
            "pack_id",
            unique=True,
        ),
        comment="Daily aggregated pack usage statistics (anonymized)",
    )


def _create_company_analytics_opt_out() -> None:
    """Create company_analytics_opt_out (GDPR opt-out registry)."""
    op.create_table(
        "company_analytics_opt_out",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="Company that opted out",
        ),
        sa.Column(
            "opted_out_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.String(length=500),
            nullable=True,
            comment="Optional reason for opt-out",
        ),
        sa.Column(
            "company_hash",
            sa.String(length=16),
            nullable=False,
            index=True,
            comment="Hashed company ID for trend removal",
        ),
        comment="Companies opted out of analytics (GDPR compliance)",
    )


def _create_benchmarking_query_logs() -> None:
    """Create benchmarking_query_logs (audit trail for cross-company analytics queries)."""
    op.create_table(
        "benchmarking_query_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "query_type",
            sa.String(length=50),
            nullable=False,
            comment="Type of query: sector_benchmarks, company_comparison, etc.",
        ),
        sa.Column(
            "query_params",
            sa.String(length=500),
            nullable=True,
            comment="Query parameters (sector, date range, etc.)",
        ),
        sa.Column(
            "queried_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Index("idx_benchmark_log_user", "user_id", "queried_at"),
        sa.Index("idx_benchmark_log_company", "company_id", "queried_at"),
        comment="Audit log for benchmarking queries (GDPR compliance)",
    )


def _create_two_factor_auth() -> None:
    """Create two_factor_auth (2FA secret storage)."""
    op.create_table(
        "two_factor_auth",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "secret",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            default=False,
            nullable=False,
        ),
        sa.Column(
            "backup_codes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "recovery_email",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "enabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            default=0,
        ),
        sa.Column(
            "locked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Index("ix_two_factor_auth_id", "id"),
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for table in (
        "two_factor_auth",
        "benchmarking_query_logs",
        "company_analytics_opt_out",
        "pack_usage_aggregates",
    ):
        if _table_exists(table):
            op.drop_table(table)
