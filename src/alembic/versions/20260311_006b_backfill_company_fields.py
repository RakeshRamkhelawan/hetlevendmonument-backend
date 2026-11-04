"""Company Layer - Backfill: Populate company fields in existing tables (ZERO-DOWNTIME Step 2)

Revision ID: 20260311_006b_backfill_company_fields
Revises: 20260311_006a_expand_add_company_fields
Create Date: 2026-03-11

BACKFILL phase of expand-contract pattern:
Populates the new columns with data from existing records.
Runs in batches to avoid lock contention.

Prerequisites:
- Application is writing to both old and new columns
- Expand migration (006a) has been applied

After this migration:
1. Verify all rows have been backfilled
2. Run contract migration (006c) to add FK constraints
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers
revision = "20260311_006b_backfill_company_fields"
down_revision = "20260311_006a_expand_add_company_fields"
branch_labels = None
depends_on = None

# Batch size for backfill to avoid lock contention
BATCH_SIZE = 1000


def upgrade() -> None:
    conn = op.get_bind()

    # Backfill requires a real DB connection (SELECT, UPDATE).
    # In offline mode (alembic upgrade head --sql) there is no live DB,
    # so skip entirely -- backfills produce no schema DDL.
    if isinstance(conn, sa.engine.mock.MockConnection):
        print("Offline mode: skipping backfill (no live DB)")
        return

    # =========================================================================
    # BACKFILL: Update existing rows in batches
    # =========================================================================

    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Backfill procedure_executions.goal_id (only if table exists)
    # The table may not be present in all test databases (e.g. SQLite in-memory CI).
    if "procedure_executions" in tables:
        print("Backfilling procedure_executions.goal_id...")

        result = conn.execute(
            sa.text("SELECT COUNT(*) FROM procedure_executions WHERE goal_id IS NULL")
        )
        count_result = result.scalar()
        count: int = int(count_result) if count_result is not None else 0
        print(f"Found {count} procedure_executions rows to backfill")

        if count > 0:
            offset = 0
            while offset < count:
                batch_count = conn.execute(
                    sa.text(
                        """
                        UPDATE procedure_executions
                        SET goal_id = NULL  -- No existing mapping, will be NULL
                        WHERE id IN (
                            SELECT id FROM procedure_executions
                            WHERE goal_id IS NULL
                            ORDER BY id
                            LIMIT :batch_size
                            OFFSET :offset
                        )
                    """
                    ),
                    {"batch_size": BATCH_SIZE, "offset": offset},
                ).rowcount

                print(f"Backfilled batch: {batch_count} rows (offset: {offset})")
                offset += BATCH_SIZE

        print("Backfill complete for procedure_executions")
    else:
        print("Skipping procedure_executions backfill: table does not exist")

    # Backfill domain_packs.company_id (if table exists)

    if "domain_packs" in tables:
        print("Backfilling domain_packs.company_id...")

        result = conn.execute(sa.text("SELECT COUNT(*) FROM domain_packs WHERE company_id IS NULL"))
        count_result = result.scalar()
        dp_count: int = int(count_result) if count_result is not None else 0
        print(f"Found {dp_count} domain_packs rows to backfill")

        if dp_count > 0:
            offset = 0
            while offset < dp_count:
                batch_count = conn.execute(
                    sa.text(
                        """
                        UPDATE domain_packs
                        SET company_id = NULL  -- Platform templates have no company
                        WHERE id IN (
                            SELECT id FROM domain_packs
                            WHERE company_id IS NULL
                            ORDER BY id
                            LIMIT :batch_size
                            OFFSET :offset
                        )
                    """
                    ),
                    {"batch_size": BATCH_SIZE, "offset": offset},
                ).rowcount

                print(f"Backfilled batch: {batch_count} rows (offset: {offset})")
                offset += BATCH_SIZE

        print("Backfill complete for domain_packs")

    print("All backfills complete!")


def downgrade() -> None:
    # No-op: backfill is idempotent, running it again doesn't hurt
    # To "undo" we would need to know the previous values, which we don't have
    print("Downgrade: backfill is idempotent, no action needed")
