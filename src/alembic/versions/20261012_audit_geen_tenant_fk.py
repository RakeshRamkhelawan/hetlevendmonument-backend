"""`audit_logs`, `ai_act_incident_reports` en `governance_authority_reports` verliezen hun vreemde sleutel naar `tenants` (AVG C).

Revision ID: 20261012_audit_geen_tenant_fk
Revises: 20261012_hr_deadlines
Create Date: 2026-10-12

Besluit Rakesh 2026-10-12: bij het opheffen van een tenant blijft het auditlog bewaard, zonder
persoonsgegevens. De vreemde sleutel `audit_logs_tenant_id_fkey` (NO ACTION) blokkeerde het
verwijderen van de tenantrij zodra er een auditregel bestond.

Alleen het SCHEMA verandert (interlock 1, aangekondigd in de dagbrief): een constraint verdwijnt,
er wordt geen rij, kolom of tabel aangeraakt en er is geen data-update. `tenant_id` blijft een gewone
integer-kolom met zijn index en zit nog steeds in de hash van elke regel; de ketenverificatie zoekt
per `tenant_id` en werkt dus ook als de tenantrij weg is.

`downgrade()` zet de constraint terug zoals hij was. Dat mislukt hardop als er inmiddels
auditregels zijn van een tenant die niet meer bestaat: die rijen moet je dan eerst bewust
verwijderen of de tenant terugzetten. Stil een ongeldige constraint toevoegen zou erger zijn.

LET OP (meld aan Rakesh): zodra de feature is gebruikt (een tenant is opgeheven) bestaan er per
definitie auditregels zonder tenantrij; terugdraaien kan dan alleen door die regels te verwijderen,
en dat is precies wat de bewaarplicht verbiedt. In de praktijk is dit dus een eenrichtingsmigratie
zodra hij is gebruikt.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261012_audit_geen_tenant_fk"
down_revision: str | None = "20261012_hr_deadlines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tabel, constraint, ondelete zoals voor deze migratie gemeten). De twee rapporttabellen blijven net
# als het auditlog bewaard (mogelijke bewaarplicht, niet gemeten) en verliezen daarom OOK hun
# vreemde sleutel naar `tenants`: ze worden bij het opheffen van een tenant geanonimiseerd.
_CONSTRAINTS = (
    ("audit_logs", "audit_logs_tenant_id_fkey", None),
    ("ai_act_incident_reports", "ai_act_incident_reports_tenant_id_fkey", "RESTRICT"),
    ("governance_authority_reports", "governance_authority_reports_tenant_id_fkey", None),
)


def upgrade() -> None:
    # IF EXISTS: ook veilig op een database waar de constraint al ontbrak (offline dry-run,
    # `scripts/init_prod_db.py`, een eerder handmatig herstel).
    for tabel, constraint, _ondelete in _CONSTRAINTS:
        op.execute(f"ALTER TABLE {tabel} DROP CONSTRAINT IF EXISTS {constraint}")


def downgrade() -> None:
    for tabel, constraint, ondelete in _CONSTRAINTS:
        op.create_foreign_key(
            constraint, tabel, "tenants", ["tenant_id"], ["id"], ondelete=ondelete
        )
