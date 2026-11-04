"""Add notifications-inbound tables to live chain, tenant_id NOT NULL, RLS

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-03

SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): src/core/notifications/
inbound/models.py's 3 tables (inbound_messages, contact_opt_outs, email_bounces)
have NO migration anywhere -- not in the live chain, not even under archive/
(confirmed via grep across src/alembic/versions/**/*.py). register_all_models()
does not import this module either, so these tables were never wired into the
Alembic-autogenerate path -- pure ORM model definitions with no corresponding
physical table until this migration.

contact_opt_outs and email_bounces had a nullable tenant_id with no documented
justification (DB-AUDIT-003 backlog). Considered and rejected a nullable
"platform-wide opt-out visible cross-tenant" design (would require exempting
both tables from the ORM auto-filter in tenant_query_filter.py, similar to the
audit_logs exemption) -- the model's own docstring ("Respected across all
channels") more plausibly means "across a tenant's own email/sms/whatsapp
channels", not "across tenants". Chose the simpler, safer, and consistent
interpretation used throughout this entire audit sprint: tenant_id NOT NULL.
inbound_messages.tenant_id was already NOT NULL in the ORM model -- unchanged.

backend-patterns.md #9: NOOIT sa.inspect(op.get_bind()) in migraties. Uses raw
"CREATE TABLE IF NOT EXISTS" / "DROP TABLE IF EXISTS" SQL, matching the
established pattern in 884d744f6aa9 / a1b2c3d4e5f6.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

_TENANT_SCOPED_TABLES = ["inbound_messages", "contact_opt_outs", "email_bounces"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inbound_messages (
            id UUID PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            channel VARCHAR(20) NOT NULL,
            provider VARCHAR(50),
            from_address VARCHAR(255) NOT NULL,
            from_name VARCHAR(255),
            to_address VARCHAR(255),
            to_addresses JSONB,
            subject VARCHAR(500),
            body_text TEXT,
            body_html TEXT,
            message_id VARCHAR(255),
            thread_id VARCHAR(255),
            in_reply_to VARCHAR(255),
            media_urls JSONB,
            status VARCHAR(50) NOT NULL DEFAULT 'unprocessed',
            intent VARCHAR(50),
            intent_confidence FLOAT,
            entities JSONB,
            routed_to VARCHAR(50),
            routing_decision JSONB,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at TIMESTAMPTZ,
            raw_payload JSONB
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_messages_tenant_id ON inbound_messages (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_messages_channel ON inbound_messages (channel)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_messages_from_address "
        "ON inbound_messages (from_address)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_messages_message_id ON inbound_messages (message_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_messages_thread_id ON inbound_messages (thread_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_inbound_messages_status ON inbound_messages (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_opt_outs (
            id UUID PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contact VARCHAR(255) NOT NULL,
            contact_type VARCHAR(20) NOT NULL,
            opted_out_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source VARCHAR(50),
            channel VARCHAR(50) NOT NULL DEFAULT 'all',
            ip_address VARCHAR(45),
            user_agent TEXT,
            inbound_message_id UUID REFERENCES inbound_messages(id) ON DELETE SET NULL,
            CONSTRAINT uq_contact_opt_outs_tenant_contact_channel
                UNIQUE (tenant_id, contact, channel)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contact_opt_outs_tenant_id ON contact_opt_outs (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contact_opt_outs_contact ON contact_opt_outs (contact)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_bounces (
            id UUID PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            original_message_id VARCHAR(255),
            bounce_message_id VARCHAR(255),
            bounce_type VARCHAR(50) NOT NULL,
            bounce_reason TEXT,
            bounce_code VARCHAR(50),
            bounced_address VARCHAR(255) NOT NULL,
            bounced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            marked_invalid BOOLEAN NOT NULL DEFAULT false,
            suppressed BOOLEAN NOT NULL DEFAULT false,
            raw_bounce_content TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_bounces_tenant_id ON email_bounces (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_bounces_original_message_id "
        "ON email_bounces (original_message_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_bounces_bounced_address "
        "ON email_bounces (bounced_address)"
    )

    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")
        op.execute(f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} USING (tenant_id = {_RLS_EXPR})")


def downgrade() -> None:
    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")

    op.execute("DROP TABLE IF EXISTS email_bounces")
    op.execute("DROP TABLE IF EXISTS contact_opt_outs")
    op.execute("DROP TABLE IF EXISTS inbound_messages")
