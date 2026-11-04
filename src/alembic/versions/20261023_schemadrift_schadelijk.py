"""Schemadrift, schadelijke gevallen: slug verruimen en drie onbekende NOT NULL-kolommen vrijgeven.

Revision ID: 20261023_schemadrift_schadelijk
Revises: 20261020_tenant_ap_verbindingen
Create Date: 2026-10-23

Alleen VERRUIMEND (interlock 1: geen DROP, geen dataverlies); bron is het rapport
`docs/backend/schemadrift-indeling-2026-10-23.md`.

- `tenants.slug` van VARCHAR(50) naar VARCHAR(100): het model belooft 100, een slug van 51 tot
  100 tekens faalde op `value too long`.
- `NOT NULL` laten vallen op drie kolommen die het model niet kent en die een insert uit het
  model dus altijd lieten stuklopen: `educational_access.code`, `study_collections.access_code`,
  `pack_usage_aggregates.company_size`. Geen kolom wordt verwijderd en geen waarde verandert.

`downgrade()` zet alles terug, maar WEIGERT met een duidelijke melding als dat gegevens zou
kosten: een slug langer dan 50 tekens, of een rij met een lege waarde in een kolom die weer
NOT NULL moet worden. Er wordt dus nooit stil afgekapt of weggegooid.

Niet in deze migratie: `pack_usage_aggregates.pack_id` (UUID met verwijzing naar `domain_packs`
tegen tekst in het model). Dat vraagt een verwijzing laten vallen en een type-omzetting waarvan
de downgrade met data niet kan; dat wacht op Rakesh.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_schemadrift_schadelijk"
down_revision: str | None = "20261020_tenant_ap_verbindingen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (tabel, kolom, lengte) van de kolommen die het model niet kent en die NOT NULL waren.
_VRIJGEGEVEN: tuple[tuple[str, str, int], ...] = (
    ("educational_access", "code", 20),
    ("study_collections", "access_code", 20),
    ("pack_usage_aggregates", "company_size", 50),
)


def upgrade() -> None:
    op.alter_column(
        "tenants",
        "slug",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    for tabel, kolom, lengte in _VRIJGEGEVEN:
        op.alter_column(tabel, kolom, existing_type=sa.String(length=lengte), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()

    te_lang = bind.execute(sa.text("SELECT count(*) FROM tenants WHERE length(slug) > 50")).scalar()
    if te_lang:
        raise RuntimeError(
            f"downgrade geweigerd: {te_lang} tenant(s) hebben een slug langer dan 50 tekens; "
            "terugzetten naar VARCHAR(50) zou die afkappen of weigeren."
        )
    for tabel, kolom, _lengte in _VRIJGEGEVEN:
        leeg = bind.execute(
            sa.text(f"SELECT count(*) FROM {tabel} WHERE {kolom} IS NULL")  # noqa: S608
        ).scalar()
        if leeg:
            raise RuntimeError(
                f"downgrade geweigerd: {tabel}.{kolom} heeft {leeg} rij(en) zonder waarde; "
                "de kolom weer NOT NULL maken zou die afwijzen."
            )

    for tabel, kolom, lengte in _VRIJGEGEVEN:
        op.alter_column(tabel, kolom, existing_type=sa.String(length=lengte), nullable=False)
    op.alter_column(
        "tenants",
        "slug",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
