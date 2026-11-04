"""ADR-029 Foundation Portal audit hardening -- persistentie contact/donaties en FORCE RLS.

Revision ID: 20260915_adr029_audit_hardening
Revises: 20260910_adr029_sprint_c_datamodel
Create Date: 2026-09-15

Remedieert bevindingen uit onafhankelijke audit ADR-029:
1. RLS-Hardening: FORCE ROW LEVEL SECURITY afdwingen op alle Foundation-tabellen met tenant_id,
   zodat tabel-eigenaren (postgres) RLS niet per ongeluk kunnen omzeilen.
2. Database-persistentie voor contactinzendingen (foundation_contact_submissions) met RLS.
3. Database-persistentie voor erfgoed-donaties en adopties (foundation_donations) met RLS.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260915_adr029_audit_hardening"
down_revision = "20260910_adr029_sprint_c_datamodel"
branch_labels = None
depends_on = None

EXISTING_RLS_TABLES = (
    "foundation_content",
    "portal_users",
    "magic_link_tokens",
    "foundation_portal_settings",
    "takedown_requests",
    "newsletter_subscriptions",
    "educational_access",
    "study_collections",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. FORCE ROW LEVEL SECURITY op alle bestaande foundation-tabellen
    # ------------------------------------------------------------------
    if _is_postgresql():
        for table in EXISTING_RLS_TABLES:
            op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

    # ------------------------------------------------------------------
    # 2. Nieuwe tabel: foundation_contact_submissions
    # ------------------------------------------------------------------
    op.create_table(
        "foundation_contact_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("reference_number", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_number", name="uq_fcs_reference_number"),
        sa.Index("idx_fcs_tenant_created", "tenant_id", "created_at"),
        sa.Index("idx_fcs_tenant_email", "tenant_id", "email"),
    )

    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE foundation_contact_submissions ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE foundation_contact_submissions FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY foundation_contact_submissions_tenant_isolation "
                "ON foundation_contact_submissions FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
            )
        )

    # ------------------------------------------------------------------
    # 3. Nieuwe tabel: foundation_donations
    # ------------------------------------------------------------------
    op.create_table(
        "foundation_donations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR", nullable=False),
        sa.Column("frequency", sa.String(20), server_default="once", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("donor_name", sa.String(255), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "adopted_content_id",
            sa.Integer(),
            sa.ForeignKey("foundation_content.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("stripe_session_id", sa.String(255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_session_id", name="uq_fd_stripe_session_id"),
        sa.Index("idx_fd_tenant_status", "tenant_id", "status"),
        sa.Index("idx_fd_tenant_created", "tenant_id", "created_at"),
        sa.Index("idx_fd_adopted_content", "tenant_id", "adopted_content_id"),
    )

    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE foundation_donations ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE foundation_donations FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY foundation_donations_tenant_isolation "
                "ON foundation_donations FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
            )
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 3. foundation_donations droppen
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS foundation_donations_tenant_isolation ON foundation_donations"
            )
        )
        op.execute(sa.text("ALTER TABLE foundation_donations NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE foundation_donations DISABLE ROW LEVEL SECURITY"))
    op.drop_table("foundation_donations")

    # ------------------------------------------------------------------
    # 2. foundation_contact_submissions droppen
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS foundation_contact_submissions_tenant_isolation ON foundation_contact_submissions"
            )
        )
        op.execute(
            sa.text("ALTER TABLE foundation_contact_submissions NO FORCE ROW LEVEL SECURITY")
        )
        op.execute(sa.text("ALTER TABLE foundation_contact_submissions DISABLE ROW LEVEL SECURITY"))
    op.drop_table("foundation_contact_submissions")

    # ------------------------------------------------------------------
    # 1. NO FORCE ROW LEVEL SECURITY op bestaande foundation-tabellen
    # ------------------------------------------------------------------
    if _is_postgresql():
        for table in EXISTING_RLS_TABLES:
            op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
