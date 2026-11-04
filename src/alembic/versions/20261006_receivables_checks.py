"""CHECK op `receivables`: bedrag niet negatief, valuta drie hoofdletters -- debiteurenagent dag 2.

Revision ID: 20261006_receivables_checks
Revises: 20261006_outgoing_messages_rls
Create Date: 2026-10-05

P2-punt uit de review van dag 1, nu de handmatige invoer erbij komt: zonder deze twee regels
kan een invoerfout een negatieve vordering of een valuta als `eur` of `EURO` opslaan, en dan
schrijft de agent een brief over een bedrag dat niet bestaat.

**Raakt een bestaande tabel, en alleen zo.** Er komen twee beperkingen bij; geen kolom of rij
wordt gewijzigd, en `downgrade()` haalt precies deze twee weer weg. Staat er al een rij die de
regel schendt, dan faalt de upgrade -- dat is geen dataverlies, maar een melding dat er eerst
iets met de hand moet worden rechtgezet. Vooraf aangekondigd in de brief van dag 2.

De valutaregel is `length(currency) = 3 AND currency = upper(currency)` en geen regex, zodat
dezelfde tekst in het model ook op SQLite (unit-tests via `create_all`) werkt. De volle
ISO-vorm (drie letters A-Z) toetst de repository. Deze migratie slaat SQLite over: daar
bestaat `ALTER TABLE ... ADD CONSTRAINT` niet.
"""

from __future__ import annotations

from alembic import op

revision = "20261006_receivables_checks"
down_revision = "20261006_outgoing_messages_rls"
branch_labels = None
depends_on = None

_TABEL = "receivables"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.create_check_constraint("ck_receivables_amount_not_negative", _TABEL, "amount >= 0")
    op.create_check_constraint(
        "ck_receivables_currency_iso",
        _TABEL,
        "length(currency) = 3 AND currency = upper(currency)",
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.drop_constraint("ck_receivables_currency_iso", _TABEL, type_="check")
    op.drop_constraint("ck_receivables_amount_not_negative", _TABEL, type_="check")
