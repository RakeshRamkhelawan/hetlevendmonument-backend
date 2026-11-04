"""Backfill prana department budgets for existing tenants (ADR-021 Fase 2).

Revision ID: 20260716_backfill_prana_budgets
Revises: 20260715_add_prana_economy_tables
Create Date: 2026-07-16

Seeds one 10000-prana budget row per canonical department for every existing tenant so
that enabling PRANA_ENFORCEMENT_ENABLED does not leave already-created tenants unfunded
(which would make the ResourceOfficer DEFER every copilot turn). Idempotent via
ON CONFLICT on uq_prana_dept_budget. New tenants are seeded live by
PranaService.provision_tenant. Genesis ledger rows are written by the live path; the
backfill seeds budgets only (the first charge starts each tenant/department hash chain).

ADR: ADR-021 (prana economy), ADR-005 (tenant isolation)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_backfill_prana_budgets"
down_revision: str | Sequence[str] | None = "20260715_add_prana_economy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Canonical PranaDepartment values (kept in sync with
# src/core/governance/prana_departments.py::PranaDepartment).
_DEPARTMENTS = [
    "strategy",
    "operations",
    "finance",
    "hr",
    "sales_marketing",
    "product_innovation",
    "it_security",
    "legal_compliance",
    "customer_experience",
    "data_ai_governance",
]


def _is_offline() -> bool:
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Data backfill against live rows -- only meaningful online on PostgreSQL.
    if _is_offline() or not _is_postgresql():
        return
    values = ", ".join(f"('{d}')" for d in _DEPARTMENTS)
    op.execute(
        sa.text(
            "INSERT INTO prana_department_budget "
            "(tenant_id, department, total_prana, allocated_prana, spent_prana, "
            " cycle_start, updated_at) "
            "SELECT t.id, d.dept, 10000, 0, 0, now(), now() "
            f"FROM tenants t CROSS JOIN (VALUES {values}) AS d(dept) "
            "ON CONFLICT ON CONSTRAINT uq_prana_dept_budget DO NOTHING"
        )
    )


def downgrade() -> None:
    # Inverse of the seeding: remove the backfilled economy data. (Rarely used; a partial
    # downgrade of a data backfill removes all budget/ledger rows.)
    if _is_offline() or not _is_postgresql():
        return
    op.execute(sa.text("DELETE FROM prana_transaction"))
    op.execute(sa.text("DELETE FROM prana_department_budget"))
