"""Eerst export, dan pas wissen: de leesbare export van ALLE tenantgegevens (AVG art. 28 lid 3 sub g).

Besluit Rakesh 2026-10-12 na `docs/onderzoek-bewaarplicht-en-opgeheven-klanten.md`: de wettelijke
bewaarplicht van facturen, loonadministratie en HR-gegevens ligt bij de KLANT, of na ontbinding bij de
bewaarder (BW 2:24) of de curator (Fw 105b). Een verwerker wist daarom niet voordat die de gegevens
heeft kunnen ophalen.

Wat bestaat en wat NIET (gemeten): `POST /api/gdpr/export` (portability_router) is een persoonlijke
inzage: alleen de eigen gebruikersrij, de eigen workflows en 90 dagen eigen auditregels. Dat is geen
administratie; er zitten geen debiteuren, geen personeelsgegevens en geen andere gebruikers in. Dit
bestand bouwt daarom een export die DOMEINONAFHANKELIJK is: elke tabel met een kolom `tenant_id`,
alle rijen van deze tenant, als JSON. Een nieuw domein hoeft hier niets voor te doen.

Grenzen, eerlijk:
- Tabellen ZONDER `tenant_id` (kindtabellen die alleen via een ouder aan een tenant hangen) staan er
  niet in. Niet gemeten welke dat zijn.
- Per tabel maximaal `MAX_RIJEN_PER_TABEL` rijen; een afgekapte tabel is gemarkeerd (`afgekapt`).
- Kolommen met `password`, `secret`, `token`, `api_key` of `private_key` in de naam blijven weg: dat
  zijn geheimen, geen administratie.
- De filter op gevoelige kolommen kijkt alleen naar kolomnamen op het hoogste niveau; een geheim
  BINNEN een JSON-kolom blijft in de export (niet gemeten welke tabellen dat raakt).
- De export is leesbaar (JSON), niet gecontroleerd op volledigheid per wettelijke eis; een jurist moet
  toetsen of dit aan BW 2:24 en Fw 105b voldoet.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import column, func, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import AuditLog

ONTVANGERS = ("klant", "bewaarder", "curator")
ACTIE_AANGEBODEN = "gdpr_tenant_export_offered"
MAX_RIJEN_PER_TABEL = 50_000
MAX_EXPORTS_PER_UUR = 5
# `encrypted_credentials` (activepieces_connections) bevatte geen van de oude woorden en ging mee in de
# export (Gate 2, 2026-10-13); `credential` en `encrypt` dekken die en soortgelijke kolommen.
GEVOELIGE_KOLOMDELEN = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "encrypt",
)
_TEKSTTYPEN = frozenset({"character varying", "text", "character"})

_TABELLEN = text(
    "SELECT c.table_name, c.data_type FROM information_schema.columns c "
    "JOIN information_schema.tables t ON t.table_schema = c.table_schema "
    "AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
    "WHERE c.column_name = 'tenant_id' AND c.table_schema = current_schema() "
    "ORDER BY c.table_name"
)


def waarde_voor_kolom(data_type: str, tenant_id: int) -> int | str:
    """De vergelijkingswaarde in het type van de kolom, zodat een index op `tenant_id` bruikbaar blijft.

    Een cast op de kolom (`CAST(tenant_id AS text)`) schakelde die index uit; alleen een echte
    tekstkolom (bv. `request_audit_logs.tenant_id`) krijgt de tekstwaarde.
    """
    return str(tenant_id) if data_type in _TEKSTTYPEN else tenant_id


def _is_gevoelig(kolomnaam: str) -> bool:
    laag = kolomnaam.lower()
    return any(deel in laag for deel in GEVOELIGE_KOLOMDELEN)


def _schoon(rij: object) -> dict[str, object]:
    waarde = json.loads(rij) if isinstance(rij, str) else rij
    return {k: v for k, v in cast("dict[str, object]", waarde).items() if not _is_gevoelig(k)}


async def bouw_tenant_dossier(db: AsyncSession, tenant_id: int) -> dict[str, dict[str, object]]:
    """{tabelnaam: {"aantal": n, "afgekapt": bool, "rijen": [...]}} voor elke tabel met `tenant_id`."""
    tabellen = [
        (str(r[0]), str(r[1]))
        for r in (await db.execute(_TABELLEN)).all()
        if str(r[0]) != "alembic_version"
    ]
    dossier: dict[str, dict[str, object]] = {}
    for naam, data_type in tabellen:
        bron = table(naam, column("tenant_id")).alias("t")
        resultaat = await db.execute(
            select(text("row_to_json(t)"))
            .select_from(bron)
            .where(bron.c.tenant_id == waarde_voor_kolom(data_type, tenant_id))
            .limit(MAX_RIJEN_PER_TABEL + 1)
        )
        rijen = [_schoon(r[0]) for r in resultaat.all()]
        afgekapt = len(rijen) > MAX_RIJEN_PER_TABEL
        if rijen:
            dossier[naam] = {
                "aantal": min(len(rijen), MAX_RIJEN_PER_TABEL),
                "afgekapt": afgekapt,
                "rijen": rijen[:MAX_RIJEN_PER_TABEL],
            }
    return dossier


def dossier_checksum(dossier: dict[str, dict[str, object]]) -> str:
    """SHA-256 over de canonieke JSON van het dossier: de ontvanger kan zijn kopie ermee controleren."""
    kanoniek = json.dumps(dossier, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(kanoniek.encode("utf-8")).hexdigest()


def telling(dossier: dict[str, dict[str, object]]) -> tuple[int, int, list[str]]:
    """(aantal tabellen, aantal rijen, namen van afgekapte tabellen)."""
    rijen = sum(int(cast("int", t["aantal"])) for t in dossier.values())
    afgekapt = [n for n, t in dossier.items() if t["afgekapt"]]
    return len(dossier), rijen, afgekapt


async def export_aangeboden(db: AsyncSession, tenant_id: int) -> bool:
    """Is er voor deze tenant ooit een export aangeboden (auditregel van de exportroute)?"""
    aantal = await db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.action == ACTIE_AANGEBODEN)
    )
    return bool(aantal)


async def export_is_te_vaak_gevraagd(db: AsyncSession, tenant_id: int) -> bool:
    """Meer dan `MAX_EXPORTS_PER_UUR` exports in het laatste uur? Dan bouwen we geen nieuwe.

    Het bouwen leest elke tenanttabel; zonder grens kan een (gestolen) beheerderssessie dat herhalen
    tot de worker vol zit. Geteld op de auditregels van de exportroute, net als de persoonlijke export.
    """
    sinds = datetime.now(timezone.utc) - timedelta(hours=1)
    aantal = await db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == ACTIE_AANGEBODEN,
            AuditLog.timestamp >= sinds,
        )
    )
    return int(aantal or 0) >= MAX_EXPORTS_PER_UUR
