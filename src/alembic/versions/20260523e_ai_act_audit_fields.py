"""Add AI Act + hash chain extension fields to governance_audit_log.

This migration adds 7 nullable columns + 1 partial index. All ALTER ops are
guarded by an inspect-based existence check so the migration is idempotent:
re-running it on a database where some columns already exist is a no-op.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260523e_ai_act_audit_fields"
down_revision = "20260523d_notification_preferences"
branch_labels = None
depends_on = None


_TABLE = "governance_audit_log"

_NEW_COLUMNS: list[tuple[str, sa.Column]] = [
    ("ai_proposal_id", sa.Column("ai_proposal_id", postgresql.UUID(as_uuid=True), nullable=True)),
    ("ai_model_id", sa.Column("ai_model_id", sa.String(64), nullable=True)),
    ("ai_model_version", sa.Column("ai_model_version", sa.String(32), nullable=True)),
    ("ai_reasoning_hash", sa.Column("ai_reasoning_hash", sa.String(64), nullable=True)),
    ("ai_data_classification", sa.Column("ai_data_classification", sa.String(16), nullable=True)),
    ("ai_explanation_summary", sa.Column("ai_explanation_summary", sa.Text(), nullable=True)),
    ("officer_verdicts_hash", sa.Column("officer_verdicts_hash", sa.String(64), nullable=True)),
]


def _is_offline(bind) -> bool:
    """Detect Alembic offline mode (CI dry-run with --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def _existing_columns(bind) -> set[str]:
    """Return set of existing column names on _TABLE, or empty set in offline mode."""
    if _is_offline(bind):
        return set()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return set()
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def _index_exists(bind, index_name: str) -> bool:
    """Return True if named index exists on _TABLE. False in offline mode."""
    if _is_offline(bind):
        return False
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(_TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    # governance_audit_log is missing on fresh databases (created by archived migration on prod)
    if not _is_offline(bind) and not sa.inspect(bind).has_table(_TABLE):
        return
    existing = _existing_columns(bind)

    for col_name, col in _NEW_COLUMNS:
        if col_name not in existing:
            # noqa: alter-column - guarded by `existing` set built from inspector.get_columns
            op.add_column(_TABLE, col)  # noqa: alter-column

    # Partial index -- only for rows with AI context (fast filter on audit views)
    if not _index_exists(bind, "idx_audit_ai_proposal"):
        op.create_index(
            "idx_audit_ai_proposal",
            _TABLE,
            ["ai_proposal_id"],
            postgresql_where=sa.text("ai_proposal_id IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "idx_audit_ai_proposal"):
        op.drop_index("idx_audit_ai_proposal", table_name=_TABLE)

    existing = _existing_columns(bind)
    for col_name, _ in reversed(_NEW_COLUMNS):
        if col_name in existing:
            op.drop_column(_TABLE, col_name)
