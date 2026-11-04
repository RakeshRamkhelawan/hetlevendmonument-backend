"""Add prana economy tables (ADR-021 department-per-tenant token economy).

Revision ID: 20260715_add_prana_economy_tables
Revises: 20260824_adr029_portal_v1
Create Date: 2026-07-15

Finding: AGENTIC-COPILOT-TAAKBEHEER-2026-07 -- prana economy Fase 1
ADR: ADR-005 (tenant_id NOT NULL + RLS), ADR-019 (hash-chain), ADR-021 (prana economy)

Herkoppeld op 2026-09-08 bij het samenvoegen van `iter/prana-economy` (Cluster F): deze
migratie wees nog naar `20260706_add_agentic_tasks_table`, de keten-kop van juli, terwijl
`develop` intussen doorliep tot `20260824_adr029_portal_v1`. Zonder herkoppeling ontstonden
twee gelijktijdige heads (`alembic heads` toonde er 2) en faalde `upgrade head --sql` met
"Multiple head revisions are present". De inhoud van deze migratie zelf is ongewijzigd.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_add_prana_economy_tables"
down_revision: str | Sequence[str] | None = "20260824_adr029_portal_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline() -> bool:
    """Detect Alembic offline (--sql) mode to skip runtime-only DDL."""
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table: str, policy: str) -> None:
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {policy} ON {table} FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )


def _disable_rls(table: str, policy: str) -> None:
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def upgrade() -> None:
    # --- prana_department_budget -------------------------------------------------
    op.create_table(
        "prana_department_budget",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("department", sa.String(length=50), nullable=False),
        sa.Column("total_prana", sa.Integer(), nullable=False, server_default=sa.text("10000")),
        sa.Column("allocated_prana", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("spent_prana", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "cycle_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "department", name="uq_prana_dept_budget"),
        sa.CheckConstraint("total_prana >= 0", name="ck_prana_total_non_negative"),
    )
    _enable_rls("prana_department_budget", "prana_budget_tenant_isolation")

    # --- prana_transaction (append-only, per-(tenant,department) hash chain) ------
    op.create_table(
        "prana_transaction",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("department", sa.String(length=50), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=255), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "data_classification",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'INTERNAL'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("tenant_id", "department", "sequence_no", name="uq_prana_tx_seq"),
        sa.CheckConstraint(
            "kind IN ('spend', 'refund', 'refill', 'emergency')", name="ck_prana_tx_kind"
        ),
    )
    op.create_index("idx_prana_tx_tenant_dept", "prana_transaction", ["tenant_id", "department"])
    op.create_index("idx_prana_tx_created", "prana_transaction", ["created_at"])
    _enable_rls("prana_transaction", "prana_tx_tenant_isolation")


def downgrade() -> None:
    _disable_rls("prana_transaction", "prana_tx_tenant_isolation")
    op.drop_index("idx_prana_tx_created", table_name="prana_transaction")
    op.drop_index("idx_prana_tx_tenant_dept", table_name="prana_transaction")
    op.drop_table("prana_transaction")

    _disable_rls("prana_department_budget", "prana_budget_tenant_isolation")
    op.drop_table("prana_department_budget")
