"""Add hitl_requests.requested_by_user_id (ADR-036 OP-81)

Revision ID: adr036_op81_requested_by
Revises: 20260716_backfill_prana_budgets
Create Date: 2026-09-01

ADR-036 OP-81: op het gatekeeper-pad kon de aanvrager zijn EIGEN goedkeuringsticket
goedkeuren. De rolcheck uit OP-43 toetst een ROL, geen RELATIE, en het ticketmodel
`HITLRequestModel` legde alleen `agent_id` vast -- WIE handelde, niet VOOR WIE. Zonder
die tweede identiteit kon de zelf-goedkeuringscheck die het broker-pad in OP-70 al
kreeg hier niet draaien.

OWASP ASVS 5.0 8.3.3 eist dat het autorisatiebesluit rust op de permissies van het
OORSPRONKELIJKE subject en niet op een tussenliggende service die namens hem handelt.
Deze kolom legt dat oorspronkelijke subject vast: het gebruikersnummer van de mens
namens wie de agent de aanvraag deed.

NULLABLE, en dat is een keuze. Bestaande rijen hebben geen aanvrager, en een aanvraag
die werkelijk zonder menselijke opdrachtgever ontstaat heeft er geen. De check slaat
dan over; de rolcheck blijft staan. Zelfde afweging als op het broker-pad.

Integer en geen tekst, om dezelfde reden als `approved_by` het gebruikersNUMMER werd
(OP-55): een e-mailadres kan de gebruiker zelf wijzigen via PUT /api/v1/users/me en is
dus geen stabiele sleutel voor een identiteitsvergelijking.

GEEN foreign key naar `users.id`: `tenant_id` en `agent_id` in deze tabel hebben er ook
geen, en een FK zou het opschonen van een gebruikersaccount laten botsen met een
bewaarde goedkeuringshistorie -- dat is een eigen besluit (retentie), niet iets om
hier binnen te smokkelen.

backend-patterns.md par. 9: NOOIT sa.inspect(op.get_bind()) in migraties (crasht bij
offline dry-run). Gebruikt daarom rauwe "ADD COLUMN IF NOT EXISTS" / "DROP COLUMN IF
EXISTS", hetzelfde patroon als c3d4e5f6a7b8 toen dat `hitl_requests.agent_id` toevoegde.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "adr036_op81_requested_by"
# Herkoppeld 2026-09-09 bij het samenvoegen van deze tak (die 252 commits achterliep).
# Oorspronkelijk hing deze migratie onder "20260824_adr029_portal_v1". Gemeten met alembic
# zelf: die revisie heeft op develop AL een kind (20260715_add_prana_economy_tables) en de
# keten loopt door naar de enige kop, 20260716_backfill_prana_budgets. Zonder herkoppelen
# zou dit een TWEEDE kop opleveren en dan weigert alembic een upgrade. Er staat al een
# migratie in deze map met precies die aantekening, dus dit is in dit project eerder misgegaan.
down_revision: Union[str, None] = "20260716_backfill_prana_budgets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Voeg de aanvragende mens toe aan hitl_requests."""
    op.execute("ALTER TABLE hitl_requests ADD COLUMN IF NOT EXISTS requested_by_user_id INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_hitl_requests_requested_by_user_id "
        "ON hitl_requests (requested_by_user_id)"
    )


def downgrade() -> None:
    """Verwijder de kolom en zijn index.

    Een echte terugweg, geen `pass`: na deze downgrade heeft de tabel weer exact het
    schema van voor deze revisie. De zelf-goedkeuringscheck valt daarmee terug op
    fail-open (de kolom is er niet meer), wat het gedrag van voor OP-81 is.
    """
    op.execute("DROP INDEX IF EXISTS ix_hitl_requests_requested_by_user_id")
    op.execute("ALTER TABLE hitl_requests DROP COLUMN IF EXISTS requested_by_user_id")
