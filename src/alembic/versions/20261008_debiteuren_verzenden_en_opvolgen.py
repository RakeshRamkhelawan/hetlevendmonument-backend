"""Debiteuren Keten B dag 1: statusvolgorde, tijdstempels en verzendlogboek.

Revision ID: 20261008_debiteuren_verzenden_en_opvolgen
Revises: 20261007_vier_ogen_bestaande_tenants
Create Date: 2026-10-06

Raakt twee bestaande tabellen.

`receivables`: kolommen `herinnerd_op` en `betaald_op` (nullable, tijdzone) erbij, en de CHECK
`ck_receivables_status` wordt vervangen door een met de waarde `geescaleerd`.

`outgoing_messages`: kolommen `verzonden_op` (nullable, tijdzone), `pogingen` (NOT NULL met
server_default 0, dus bestaande rijen krijgen 0) en `foutreden` (nullable) erbij.

De upgrade is additief en laat geen rij ongemoeid-onbruikbaar achter. De downgrade RAAKT DATA:
de oude CHECK kent `geescaleerd` niet, dus rijen met die status worden eerst op `herinnerd`
gezet. Dat is bewust en vooraf aangekondigd; akkoord Rakesh 2026-10-06 (interlock 1, zie de
brief `2026-10-06-sprint-dag-debiteuren-keten-b-verzenden-en-opvolgen.md`, "Vooraankondiging").
De inhoud van de vijf nieuwe kolommen gaat bij de downgrade verloren.

Deze migratie slaat SQLite over (unit-tests bouwen het schema via `create_all`; daar bestaat
`ALTER TABLE ... ADD CONSTRAINT` niet).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261008_debiteuren_verzenden_en_opvolgen"
down_revision = "20261007_vier_ogen_bestaande_tenants"
branch_labels = None
depends_on = None

_RECEIVABLES = "receivables"
_OUTGOING = "outgoing_messages"
_CHECK = "ck_receivables_status"
_CHECK_NIEUW = "status IN ('open', 'herinnerd', 'geescaleerd', 'betaald')"
_CHECK_OUD = "status IN ('open', 'herinnerd', 'betaald')"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.add_column(_RECEIVABLES, sa.Column("herinnerd_op", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_RECEIVABLES, sa.Column("betaald_op", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(_CHECK, _RECEIVABLES, type_="check")
    op.create_check_constraint(_CHECK, _RECEIVABLES, _CHECK_NIEUW)

    op.add_column(_OUTGOING, sa.Column("verzonden_op", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        _OUTGOING,
        sa.Column("pogingen", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(_OUTGOING, sa.Column("foutreden", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.drop_column(_OUTGOING, "foutreden")
    op.drop_column(_OUTGOING, "pogingen")
    op.drop_column(_OUTGOING, "verzonden_op")

    # WHY: de oude CHECK kent `geescaleerd` niet; zonder deze UPDATE faalt het terugzetten.
    # Bewust data-rakend, akkoord Rakesh 2026-10-06 (brief, "Vooraankondiging").
    op.execute("UPDATE receivables SET status = 'herinnerd' WHERE status = 'geescaleerd'")
    op.drop_constraint(_CHECK, _RECEIVABLES, type_="check")
    op.create_check_constraint(_CHECK, _RECEIVABLES, _CHECK_OUD)
    op.drop_column(_RECEIVABLES, "betaald_op")
    op.drop_column(_RECEIVABLES, "herinnerd_op")
