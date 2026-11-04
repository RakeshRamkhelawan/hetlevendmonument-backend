"""ADR-029 Sprint C datamodel-uitbreiding -- visibility, ContentType-waarden, target_age_group.

Revision ID: 20260910_adr029_sprint_c_datamodel
Revises: 20260909_adr029_edu_alignment
Create Date: 2026-09-10

BE-MIG-014 (spec docs/backend/features/BE-MIG-014-sprint-c-datamodel.md).
Maakt het datamodel geschikt voor educatieve content voordat de
edu-endpoints (Sprint D / BE-EP-039) gebouwd worden. Kern-eis uit audit
N-2: edu-content mag NOOIT in het publieke archief verschijnen; dat vereist
een expliciet visibility-veld, geen hergebruik van privacy (O1).

Wat deze migratie doet:
1. autocommit-blok: nieuwe Postgres-enum visibility_enum ('public', 'edu',
   'community') plus zes nieuwe waarden op content_type_enum. Postgres staat
   gebruik van een nieuwe enum-waarde niet toe in dezelfde transactie als
   het ALTER TYPE ... ADD VALUE (audit regels 150-153), daarom autocommit +
   IF NOT EXISTS (idempotent, O3).
2. Gewone transactie: kolommen visibility (NOT NULL, default 'public') en
   target_age_group (String(50), nullable), backfill vanuit privacy met
   defensieve CASE-cast en rowcount-verificatie (O2), index
   idx_fc_tenant_visibility_status op (tenant_id, visibility, status) (O7).

Casing-afwijking t.o.v. de letterlijke spec-tekst (O5 noemt lowercase):
content_type_enum bevat in de database de member-NAMEN in hoofdletters
(STORY, ARTWORK, ...) en het ORM serialiseert zonder values_callable ook
member-namen. Lowercase waarden toevoegen zou dode duplicaten geven (exact
de 'bounced'-bug die BE-MIG-013 opruimde) en ORM-inserts zouden falen op de
ontbrekende hoofdletterwaarde. De zes waarden worden daarom als
hoofdletters toegevoegd: VIDEO, EDUCATIONAL_WORKBOOK, EDUCATIONAL_VIDEO,
TEACHER_GUIDE, EVENT_REPORT, ART_DOCUMENTATION. visibility_enum is WEL
lowercase: die kolom krijgt values_callable in het model (O6).

Downgrade: index, kolommen en visibility_enum worden gedropt. De zes nieuwe
content_type_enum-waarden blijven staan: PostgreSQL kan enum-waarden niet
verwijderen zonder het type te recreeen, en content_type_enum wordt breed
gebruikt -- recreatie is een onnodig risico voor een downgrade. Ze zijn
onbereikbaar zolang de model-waarden er niet zijn.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260910_adr029_sprint_c_datamodel"
down_revision = "20260909_adr029_edu_alignment"
branch_labels = None
depends_on = None

# Nieuwe content_type_enum-waarden als member-NAMEN (hoofdletters): het type
# bevat STORY/ARTWORK/... en het ORM serialiseert zonder values_callable
# member-namen. Zie module-docstring.
NEW_CONTENT_TYPE_VALUES = (
    "VIDEO",
    "EDUCATIONAL_WORKBOOK",
    "EDUCATIONAL_VIDEO",
    "TEACHER_GUIDE",
    "EVENT_REPORT",
    "ART_DOCUMENTATION",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Enum-type en -waarden in autocommit (O3). Postgres staat gebruik
    #    van een net toegevoegde enum-waarde niet toe binnen dezelfde
    #    transactie als het ALTER TYPE.
    # ------------------------------------------------------------------
    if _is_postgresql():
        with op.get_context().autocommit_block():
            # Geen CREATE TYPE IF NOT EXISTS in Postgres; DO-blok met
            # duplicate_object-vangst is het idempotente equivalent.
            op.execute(
                sa.text(
                    "DO $$ BEGIN "
                    "CREATE TYPE visibility_enum AS ENUM ('public', 'edu', 'community'); "
                    "EXCEPTION WHEN duplicate_object THEN NULL; "
                    "END $$"
                )
            )
            for value in NEW_CONTENT_TYPE_VALUES:
                op.execute(
                    sa.text(
                        f"ALTER TYPE content_type_enum ADD VALUE IF NOT EXISTS '{value}'"
                    )
                )

    # ------------------------------------------------------------------
    # 2. Kolommen in de gewone transactie (O2, O4).
    # ------------------------------------------------------------------
    op.add_column(
        "foundation_content",
        sa.Column(
            "visibility",
            sa.Enum("public", "edu", "community", name="visibility_enum"),
            server_default="public",
            nullable=False,
        ),
    )
    op.add_column(
        "foundation_content",
        sa.Column("target_age_group", sa.String(50), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. Backfill visibility vanuit privacy met defensieve CASE-cast (O2).
    #    privacy_enum bevat hoofdletter member-namen; onbekende waarden
    #    vallen terug op 'public' (veilige default).
    # ------------------------------------------------------------------
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "UPDATE foundation_content SET visibility = "
            "(CASE privacy::text "
            "WHEN 'PUBLIC' THEN 'public' "
            "WHEN 'COMMUNITY' THEN 'community' "
            "ELSE 'public' END)::visibility_enum"
        )
    )
    if result is not None:
        # Offline mode (--sql) levert geen rowcount; dan skippen we de check.
        updated = result.rowcount
        count_result = bind.execute(sa.text("SELECT count(*) FROM foundation_content"))
        if count_result is not None and updated != -1:
            total = count_result.scalar_one()
            if updated != total:
                raise RuntimeError(
                    f"Backfill visibility raakte {updated} rijen maar foundation_content "
                    f"heeft er {total} -- migratie stopt hard i.p.v. stil verder te gaan"
                )
            print(f"[BE-MIG-014] backfill visibility: {updated} rijen bijgewerkt")

    # ------------------------------------------------------------------
    # 4. Index voor de Sprint-D edu-lijstquery (O7).
    # ------------------------------------------------------------------
    op.create_index(
        "idx_fc_tenant_visibility_status",
        "foundation_content",
        ["tenant_id", "visibility", "status"],
    )


def downgrade() -> None:
    # Index en kolommen terug. De zes nieuwe content_type_enum-waarden
    # blijven bewust staan: PostgreSQL kan enum-waarden niet verwijderen
    # zonder type-recreatie (zie module-docstring).
    op.drop_index("idx_fc_tenant_visibility_status", table_name="foundation_content")
    op.drop_column("foundation_content", "target_age_group")
    op.drop_column("foundation_content", "visibility")
    if _is_postgresql():
        op.execute(sa.text("DROP TYPE IF EXISTS visibility_enum"))
