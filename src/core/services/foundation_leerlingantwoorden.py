"""Leerlingantwoorden: controle bij het opslaan en verwijderen na 8 weken (BE-EP-055).

Privacy (minderjarigen, AVG): een leerling geeft alleen een voornaam of bijnaam op. Antwoorden
worden 8 weken na het eerste opslaan (`created_at`) verwijderd. Twee plekken zorgen daarvoor:

1. de API ruimt bij elk lezen en schrijven de verlopen rijen van de eigen tenant op, zodat
   niemand ooit een antwoord ouder dan 8 weken ziet;
2. de dagelijkse Container App Job `levendmonument-opschonen` draait dit bestand als module
   (`python3 -m src.core.services.foundation_leerlingantwoorden`) met de
   EIGENAAR-verbinding en verwijdert de verlopen rijen van alle tenants, ook als niemand de
   site bezoekt.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.models.foundation_content import FoundationStudentAnswer

#: Bewaartermijn, gerekend vanaf het eerste opslaan.
BEWAARTERMIJN = timedelta(weeks=8)

#: Grenzen voor wat een leerling kan opsturen.
MAX_NAAM = 40
MAX_ANTWOORD = 2000


class OngeldigAntwoord(ValueError):
    """De invoer van de leerling voldoet niet (de API maakt er een 422 van)."""


def grens(nu: datetime) -> datetime:
    """Rijen met `created_at` voor dit moment zijn verlopen."""
    return nu - BEWAARTERMIJN


async def verwijder_verlopen_antwoorden(
    sessie: AsyncSession, nu: datetime, tenant_id: int | None = None
) -> int:
    """Verwijder antwoorden ouder dan de bewaartermijn; geeft het aantal verwijderde rijen.

    Met `tenant_id` alleen die tenant (API); zonder alle tenants (dagelijkse job, eigenaar).
    """
    stmt = delete(FoundationStudentAnswer).where(FoundationStudentAnswer.created_at < grens(nu))
    if tenant_id is not None:
        stmt = stmt.where(FoundationStudentAnswer.tenant_id == tenant_id)
    resultaat = await sessie.execute(stmt)
    return int(getattr(resultaat, "rowcount", 0) or 0)


def hash_leerlingtoken(token: str) -> str:
    """De browser bewaart een willekeurig token; de database alleen de hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def schoon_naam(naam: str) -> str:
    """Een voornaam of bijnaam: verplicht, maximaal 40 tekens, geen e-mailadres."""
    schoon = " ".join(naam.split())
    if not schoon:
        raise OngeldigAntwoord("Vul je voornaam of een bijnaam in.")
    if len(schoon) > MAX_NAAM:
        raise OngeldigAntwoord(f"Je naam mag maximaal {MAX_NAAM} tekens zijn.")
    if "@" in schoon:
        raise OngeldigAntwoord("Vul alleen je voornaam of een bijnaam in, geen e-mailadres.")
    return schoon


def schoon_antwoorden(
    antwoorden: dict[str, str], vragen: list[dict[str, object]]
) -> dict[str, str]:
    """Houd alleen antwoorden op vragen die op het werkblad staan, ingekort en als tekst.

    Onbekende sleutels zijn een fout: zo kan niemand willekeurige velden in de tabel zetten.
    """
    toegestaan = {str(v.get("sleutel")) for v in vragen if v.get("sleutel")}
    onbekend = set(antwoorden) - toegestaan
    if onbekend:
        raise OngeldigAntwoord(f"Onbekende vraag: {', '.join(sorted(onbekend))}")
    schoon: dict[str, str] = {}
    for sleutel, waarde in antwoorden.items():
        tekst = str(waarde or "").strip()
        if len(tekst) > MAX_ANTWOORD:
            raise OngeldigAntwoord(f"Een antwoord mag maximaal {MAX_ANTWOORD} tekens zijn.")
        if tekst:
            schoon[sleutel] = tekst
    return schoon


async def _main() -> None:
    # BE-EP-056: dezelfde nachtelijke job ruimt ook ongebruikte vertelleraccounts op.
    from src.core.services.foundation_accounts import verwijder_ongebruikte_accounts

    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"ssl": "require"})
    aantal = 0
    accounts = 0
    try:
        nu = datetime.now(timezone.utc)
        async with AsyncSession(engine) as sessie:
            tenant_ids = [
                int(t)
                for t in (await sessie.execute(text("SELECT id FROM tenants ORDER BY id")))
                .scalars()
                .all()
            ]
        # FORCE ROW LEVEL SECURITY geldt ook voor de eigenaar-verbinding: zonder tenantcontext
        # ziet deze job nul rijen en verwijdert hij stil niets. Daarom per tenant een eigen
        # transactie met app.current_tenant gezet (is_local: alleen voor die transactie).
        for tenant_id in tenant_ids:
            async with AsyncSession(engine) as sessie:
                await sessie.execute(
                    text("SELECT set_config('app.current_tenant', :tenant, true)"),
                    {"tenant": str(tenant_id)},
                )
                aantal += await verwijder_verlopen_antwoorden(sessie, nu, tenant_id)
                accounts += await verwijder_ongebruikte_accounts(sessie, nu, tenant_id)
                await sessie.commit()
        print(f"leerlingantwoorden verwijderd (ouder dan 8 weken): {aantal}")
        print(f"ongebruikte vertelleraccounts verwijderd (link nooit gebruikt, ouder dan 7 dagen): {accounts}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
