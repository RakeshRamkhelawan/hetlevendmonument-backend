"""Vier ogen: bestaande ondernemingen krijgen de standaard, eenmalig (ADR-039, Rakesh 2026-10-05).

Revision ID: 20261007_vier_ogen_bestaande_tenants
Revises: 20261006_receivables_checks
Create Date: 2026-10-05

Besluit Rakesh (ADR-039, "Bestaande ondernemingen"): ook bestaande ondernemingen krijgen de
vier-ogen-standaard, zolang bij het inrichten duidelijk wordt wat de keuzes zijn. Daarom zet
deze migratie naast de standaard ook een markering die het scherm met uitleg laat verschijnen
bij de eerste keer dat een beheerder inlogt.

**Wat er gebeurt, per rij in `tenants`:**
- `settings` is NULL of een object ZONDER `four_eyes_actions`: de standaardlijst erbij, plus
  `four_eyes_explanation_pending: true`, plus het merkteken `four_eyes_set_by_migration`
  (deze revisie, en of `settings` NULL was).
- de sleutel bestaat al (ook een lege lijst), of `settings` is geen object: niets.

Geen andere kolom, geen ander tenantveld. **`downgrade()`** raakt alleen rijen met het
merkteken van deze revisie en haalt precies die drie sleutels weg; was `settings` NULL, dan
wordt het weer NULL. Wie na de upgrade zelf iets koos via `PUT /four-eyes`, verliest het
merkteken (`write_four_eyes_actions`) en blijft bij een downgrade ongemoeid.

De lijst staat hier letterlijk en wordt NIET uit `rbac_models` geimporteerd: een migratie
legt vast wat er op dat moment gebeurde en mag niet meebewegen met latere code. Rij voor rij
in Python en niet in SQL: de kolom is `json` (geen `jsonb`), en zo werkt het ook op SQLite.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20261007_vier_ogen_bestaande_tenants"
down_revision = "20261006_receivables_checks"
branch_labels = None
depends_on = None

_SLEUTEL = "four_eyes_actions"
_UITLEG = "four_eyes_explanation_pending"
_MERK = "four_eyes_set_by_migration"
_STANDAARD = [
    "query_hr_database",
    "analyze_skill_gap",
    "schedule_training",
    "make_payment",
    "change_iban",
    "write_off_receivable",
    "transfer_to_debt_collection",
]


def _lees(waarde: object) -> object:
    """Een json-kolom komt per driver als dict of als tekst binnen."""
    if isinstance(waarde, str):
        return json.loads(waarde)
    return waarde


def _offline() -> bool:
    """`alembic upgrade head --sql` heeft geen rijen om te lezen; daar doet deze migratie niets.

    Gemeten: zonder deze toets faalde
    `tests/architecture/test_named_columns_exist_in_the_migration_chain.py`
    (`'NoneType' object has no attribute 'all'`). Er is geen schemawijziging om uit te schrijven.
    """
    return bool(op.get_context().as_sql)


def _rijen() -> list[tuple[int, object]]:
    rows = op.get_bind().execute(sa.text("SELECT id, settings FROM tenants")).all()
    return [(int(r[0]), _lees(r[1])) for r in rows]


def _schrijf(tenant_id: int, settings: dict[str, object] | None) -> None:
    if settings is None:
        op.get_bind().execute(
            sa.text("UPDATE tenants SET settings = NULL WHERE id = :id"), {"id": tenant_id}
        )
        return
    op.get_bind().execute(
        sa.text("UPDATE tenants SET settings = CAST(:s AS json) WHERE id = :id"),
        {"s": json.dumps(settings), "id": tenant_id},
    )


def upgrade() -> None:
    if _offline():
        return
    for tenant_id, settings in _rijen():
        if settings is not None and not isinstance(settings, dict):
            continue
        if isinstance(settings, dict) and _SLEUTEL in settings:
            continue
        nieuw: dict[str, object] = dict(settings or {})
        nieuw[_SLEUTEL] = list(_STANDAARD)
        nieuw[_UITLEG] = True
        nieuw[_MERK] = {"revision": revision, "settings_was_null": settings is None}
        _schrijf(tenant_id, nieuw)


def downgrade() -> None:
    if _offline():
        return
    for tenant_id, settings in _rijen():
        if not isinstance(settings, dict):
            continue
        merk = settings.get(_MERK)
        if not isinstance(merk, dict) or merk.get("revision") != revision:
            continue
        rest = {k: v for k, v in settings.items() if k not in (_SLEUTEL, _UITLEG, _MERK)}
        _schrijf(tenant_id, None if merk.get("settings_was_null") is True and not rest else rest)
