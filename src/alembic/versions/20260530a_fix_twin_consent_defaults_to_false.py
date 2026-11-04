"""fix_twin_consent_defaults_to_false

Revision ID: 20260530a
Revises: 20260529e
Create Date: 2026-05-30

GDPR Art. 7 compliance: consent must be explicit opt-in.
Changes server_default from TRUE/enabled to FALSE/disabled on all consent columns.
Only affects NEW rows (ALTER COLUMN SET DEFAULT); no UPDATE of existing data.
"""

from alembic import op

# revision identifiers
revision = "20260530a"
down_revision = "20260529e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Zero-downtime: ALTER COLUMN SET DEFAULT only changes the default for new rows,
    # no table rewrite or locking needed in PostgreSQL.
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN consent_given SET DEFAULT false")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN status SET DEFAULT 'disabled'")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN behavior_tracking SET DEFAULT false")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN profile_aggregation SET DEFAULT false")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN ai_interventions SET DEFAULT false")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN cross_session_memory SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN consent_given SET DEFAULT true")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN status SET DEFAULT 'enabled'")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN behavior_tracking SET DEFAULT true")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN profile_aggregation SET DEFAULT true")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN ai_interventions SET DEFAULT true")
    op.execute("ALTER TABLE user_twin_consent ALTER COLUMN cross_session_memory SET DEFAULT true")
