"""Company Layer - Contract: Add FK constraints (ZERO-DOWNTIME Step 3)

Revision ID: 20260311_006c_contract_add_fk_constraints
Revises: 20260311_006b_backfill_company_fields
Create Date: 2026-03-11

CONTRACT phase of expand-contract pattern:
Adds foreign key constraints after all data has been backfilled.

Prerequisites:
- Expand migration (006a) applied
- Backfill migration (006b) completed successfully
- All rows have valid values in new columns

After this migration:
- FK constraints are enforced
- Application can stop writing to old columns
- Eventually old columns can be removed (future migration)
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers
revision = "20260311_006c_contract_add_fk_constraints"
down_revision = "20260311_006b_backfill_company_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_offline = isinstance(conn, sa.engine.mock.MockConnection)

    # =========================================================================
    # CONTRACT: Add FK constraints
    # =========================================================================

    # FK constraints require online mode (database handles table recreation for SQLite).
    # In offline mode, emit SQL comments for documentation purposes only.
    if is_offline:
        op.execute(
            sa.text(
                "-- Contract phase: Add FK constraint procedure_executions.goal_id -> goals.id "
                "(online only - requires database connection)"
            )
        )
        op.execute(
            sa.text(
                "-- Contract phase: Add FK constraint domain_packs.company_id -> companies.id "
                "(online only - requires database connection)"
            )
        )
        return

    tables = sa.inspect(conn).get_table_names()

    # Add FK constraint to procedure_executions.goal_id (if both tables exist)
    # Both source and target must exist; database handles table recreation if needed.
    if "procedure_executions" in tables and "goals" in tables:
        print("Adding FK constraint to procedure_executions.goal_id...")
        op.create_foreign_key(
            "fk_procedure_executions_goal",
            "procedure_executions",
            "goals",
            ["goal_id"],
            ["id"],
            ondelete="SET NULL",
        )
        print("FK constraint added to procedure_executions")
    else:
        print("Skipping FK on procedure_executions: table(s) do not exist")

    # Add FK constraint to domain_packs.company_id (if tables exist)
    if "domain_packs" in tables and "companies" in tables:
        print("Adding FK constraint to domain_packs.company_id...")
        op.create_foreign_key(
            "fk_domain_packs_company",
            "domain_packs",
            "companies",
            ["company_id"],
            ["id"],
            ondelete="SET NULL",
        )
        print("FK constraint added to domain_packs")


def downgrade() -> None:
    conn = op.get_bind()
    is_offline = isinstance(conn, sa.engine.mock.MockConnection)

    # Drop FK constraints in reverse order.
    # In offline mode, constraints were never created (see upgrade()), so skip.
    if is_offline:
        return

    tables_down = sa.inspect(conn).get_table_names()

    if "domain_packs" in tables_down:
        op.drop_constraint("fk_domain_packs_company", "domain_packs", type_="foreignkey")

    if "procedure_executions" in tables_down:
        op.drop_constraint(
            "fk_procedure_executions_goal", "procedure_executions", type_="foreignkey"
        )
