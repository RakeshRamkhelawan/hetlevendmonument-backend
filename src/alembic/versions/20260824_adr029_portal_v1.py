"""ADR-029 Foundation Portal v1 -- model uitbreidingen.

Revision ID: 20260824_adr029_portal_v1
Revises: 20260818_rls_index
Create Date: 2026-08-24

Wijzigingen:
- foundation_content: +lat, +lng, +location_name, +license, +category, +metadata (JSONB)
- portal_users: +role (enum), +email_verified, +consent_given, +consent_given_at
- Nieuwe tabel: educational_access (met RLS)
- Nieuwe tabel: study_collections (met RLS)
- newsletter_status_enum: +BOUNCED
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260824_adr029_portal_v1"
down_revision = "20260822_hr_trainings_tables"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. newsletter_status_enum uitbreiden met BOUNCED
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text(
                "ALTER TYPE newsletter_status_enum ADD VALUE IF NOT EXISTS 'bounced'"
            )
        )

    # ------------------------------------------------------------------
    # 2. foundation_content velden toevoegen
    # ------------------------------------------------------------------
    op.add_column(
        "foundation_content",
        sa.Column("lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "foundation_content",
        sa.Column("lng", sa.Float(), nullable=True),
    )
    op.add_column(
        "foundation_content",
        sa.Column("location_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "foundation_content",
        sa.Column("license", sa.String(50), nullable=True),
    )
    op.add_column(
        "foundation_content",
        sa.Column("category", sa.String(100), nullable=True),
    )
    op.add_column(
        "foundation_content",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Geo index voor lat/lng (expression index, werkt zonder PostGIS)
    if _is_postgresql():
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_fc_geo "
                "ON foundation_content USING gist (point(lng, lat)) "
                "WHERE lat IS NOT NULL AND lng IS NOT NULL"
            )
        )

    # GIN index voor metadata JSONB
    if _is_postgresql():
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_fc_metadata "
                "ON foundation_content USING gin (metadata)"
            )
        )

    # ------------------------------------------------------------------
    # 3. portal_users velden toevoegen
    # ------------------------------------------------------------------
    portal_role_enum = sa.Enum(
        "admin",
        "curator",
        "teacher",
        "student",
        "visitor",
        name="portal_role_enum",
        create_type=False,
    )
    # `op.add_column` doet, anders dan `op.create_table`, GEEN CREATE TYPE voor een
    # inline sa.Enum -- die moet expliciet aangemaakt worden, anders faalt de ALTER TABLE
    # met "type portal_role_enum does not exist" (empirisch bevestigd tegen een echte
    # Postgres, niet aangenomen). `create_type=False` op het Enum-object voorkomt dat
    # add_column het zelf nog een keer probeert aan te maken.
    portal_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "portal_users",
        sa.Column(
            "role",
            portal_role_enum,
            nullable=False,
            server_default="visitor",
        ),
    )
    op.add_column(
        "portal_users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "portal_users",
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "portal_users",
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 4. Nieuwe tabel: educational_access
    # ------------------------------------------------------------------
    op.create_table(
        "educational_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column(
            "role",
            sa.Enum("teacher", "student", "admin", "curator", "visitor", name="educational_role_enum"),
            nullable=False,
            server_default="student",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_ea_tenant_code", "tenant_id", "code", unique=True),
        sa.Index("idx_ea_tenant_email", "tenant_id", "email"),
    )

    # RLS voor educational_access -- safe NULLIF pattern (ADR-005)
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE educational_access ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY educational_access_tenant_isolation "
                "ON educational_access FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
            )
        )

    # ------------------------------------------------------------------
    # 5. Nieuwe tabel: study_collections
    # ------------------------------------------------------------------
    op.create_table(
        "study_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("access_code", sa.String(20), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("idx_sc_tenant_code", "tenant_id", "access_code"),
    )

    # RLS voor study_collections -- safe NULLIF pattern (ADR-005)
    if _is_postgresql():
        op.execute(sa.text("ALTER TABLE study_collections ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY study_collections_tenant_isolation "
                "ON study_collections FOR ALL "
                "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)"
            )
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 5. study_collections
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text("DROP POLICY IF EXISTS study_collections_tenant_isolation ON study_collections")
        )
        op.execute(sa.text("ALTER TABLE study_collections DISABLE ROW LEVEL SECURITY"))
    op.drop_table("study_collections")

    # ------------------------------------------------------------------
    # 4. educational_access
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(
            sa.text("DROP POLICY IF EXISTS educational_access_tenant_isolation ON educational_access")
        )
        op.execute(sa.text("ALTER TABLE educational_access DISABLE ROW LEVEL SECURITY"))
    op.drop_table("educational_access")
    # Opruimen van het enum type (PostgreSQL laat orphaned enums achter)
    if _is_postgresql():
        op.execute(sa.text("DROP TYPE IF EXISTS educational_role_enum"))

    # ------------------------------------------------------------------
    # 3. portal_users velden verwijderen
    # ------------------------------------------------------------------
    op.drop_column("portal_users", "consent_given_at")
    op.drop_column("portal_users", "consent_given")
    op.drop_column("portal_users", "email_verified")
    op.drop_column("portal_users", "role")
    # Opruimen van het enum type, zelfde reden als educational_role_enum hierboven.
    if _is_postgresql():
        op.execute(sa.text("DROP TYPE IF EXISTS portal_role_enum"))

    # ------------------------------------------------------------------
    # 2. foundation_content velden verwijderen
    # ------------------------------------------------------------------
    if _is_postgresql():
        op.execute(sa.text("DROP INDEX IF EXISTS idx_fc_metadata"))
        op.execute(sa.text("DROP INDEX IF EXISTS idx_fc_geo"))
    op.drop_column("foundation_content", "metadata")
    op.drop_column("foundation_content", "category")
    op.drop_column("foundation_content", "license")
    op.drop_column("foundation_content", "location_name")
    op.drop_column("foundation_content", "lng")
    op.drop_column("foundation_content", "lat")

    # ------------------------------------------------------------------
    # 1. Enum waarde verwijderen -- PostgreSQL ondersteunt dit niet native
    #    We laten 'bounced' staan; het is backwards-compatibel.
    # ------------------------------------------------------------------
    pass
