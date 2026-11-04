"""De tenantcontext moet ELKE transactie van een sessie dekken, niet alleen de eerste.

ADR-036 OP-151. Gemeten op 2026-08-16 tegen PostgreSQL 15:

    SET LOCAL app.current_tenant = '42'   -> current_setting(...) = '42'
    commit()                              -> current_setting(...) = ''      <-- weg
    SET app.current_tenant = '42' (zonder LOCAL), commit() -> '42'          <-- blijft

`SET LOCAL` is transactie-gebonden. `src/core/database/database.py` zette hem eenmalig
direct na het aanmaken van de sessie, dus zodra een endpoint zelf `await db.commit()` doet
-- en dat is de normale gang van zaken -- draaide de rest van dat verzoek ZONDER
tenantcontext verder.

Vandaag valt dat niet op: de applicatie verbindt als tabeleigenaar en PostgreSQL slaat
Row Level Security voor de eigenaar over. Zodra de applicatie een eigen rol krijgt
(OP-151) wordt het zichtbaar, en wel op de vervelendste manier die er is:

    tabel met de veilige policyvorm  -> NULLIF('', '')::INTEGER = NULL -> NUL RIJEN
    tabel met de oude policyvorm     -> ''::integer -> InvalidTextRepresentation

Geen van beide is een leesbare fout. De eerste is stille gegevensloosheid.

De oplossing is een `begin`-event op de engine, zodat elke transactie de context opnieuw
zet. Deze test legt het GEDRAG vast, niet dat mechanisme -- een andere oplossing die de
context per transactie zet mag deze test net zo goed groen maken.

**Mutatiebewijs (2026-08-16), beide richtingen:**
- Het `begin`-event uit `database.py` gehaald -> `test_the_tenant_context_survives_a_commit`
  ROOD met `''` in plaats van het tenantnummer.
- Het event de ContextVar laten negeren en altijd een vaste tenant zetten ->
  `test_a_session_without_a_tenant_gets_no_tenant_context` ROOD. Zonder die helft zou
  "zet altijd tenant 1" een geldige oplossing zijn, en dat is precies een lek.
"""

from __future__ import annotations

import os
import socket

import pytest
from sqlalchemy import text
from tests.fixtures.testdatabase import testdatabase_poort


def _postgres_bereikbaar() -> bool:
    poort = testdatabase_poort()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", poort)) == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op POSTGRES_PORT (standaard 5455)",
    ),
]


@pytest.mark.asyncio
async def test_the_tenant_context_survives_a_commit() -> None:
    """Na een commit binnen dezelfde sessie staat de tenantcontext er nog steeds."""
    from src.core.database.database import db_manager
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

    set_tenant_id(4242)
    try:
        async with db_manager.get_session() as sessie:
            await sessie.commit()

            resultaat = await sessie.execute(
                text("SELECT current_setting('app.current_tenant', true)")
            )
            na_commit = resultaat.scalar()
    finally:
        clear_tenant_context()

    assert na_commit == "4242", (
        f"Na een commit staat app.current_tenant op {na_commit!r} in plaats van '4242'. "
        "Elke query daarna draait zonder tenantcontext; onder een applicatierol levert dat "
        "nul rijen op tabellen met de veilige policyvorm en een InvalidTextRepresentation "
        "op de oudere vorm (ADR-036 OP-151)."
    )


@pytest.mark.asyncio
async def test_a_session_without_a_tenant_gets_no_tenant_context() -> None:
    """De andere richting: zonder tenant in de ContextVar wordt er niets geerfd.

    Zonder deze helft zou 'zet altijd een vaste tenant' de test hierboven halen. Dat is
    geen oplossing maar een lek: een achtergrondtaak zou dan de gegevens van die tenant
    zien.

    De eerste versie van deze test gebruikte `db_manager` en dwong daarmee NIET af dat
    beide sessies dezelfde fysieke verbinding krijgen -- met een pool groter dan een kon
    hij groen zijn zonder iets te bewijzen (Gate 2-review 2026-08-16, en precies de
    vacuum-vorm uit `.claude/rules/quality-gates.md`). Vandaar een eigen engine met
    `pool_size=1, max_overflow=0`: de tweede sessie KRIJGT gegarandeerd de verbinding
    terug waarop de eerste tenant 4242 heeft gezet. `pg_backend_pid()` legt dat vast in
    de assertie, zodat een latere wijziging aan de poolinstelling de test niet stilletjes
    hol maakt.

    Dat deze eigen engine dezelfde bescherming krijgt is geen toeval maar het punt: het
    `begin`-event hangt aan de klasse `Engine` en dekt daarmee ook de zestien engines die
    de codebase buiten `db_manager` om bouwt.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core.config.unified_config import config
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

    url = str(config.get_database_config()["url"])
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    maak_sessie = async_sessionmaker(engine, expire_on_commit=False)

    try:
        set_tenant_id(4242)
        async with maak_sessie() as sessie:
            eerste_pid = (await sessie.execute(text("SELECT pg_backend_pid()"))).scalar()
            gezet = (
                await sessie.execute(text("SELECT current_setting('app.current_tenant', true)"))
            ).scalar()
            await sessie.commit()

        clear_tenant_context()

        async with maak_sessie() as sessie:
            tweede_pid = (await sessie.execute(text("SELECT pg_backend_pid()"))).scalar()
            zonder_tenant = (
                await sessie.execute(text("SELECT current_setting('app.current_tenant', true)"))
            ).scalar()
            await sessie.commit()
    finally:
        clear_tenant_context()
        await engine.dispose()

    assert gezet == "4242", (
        f"De eerste sessie kreeg app.current_tenant = {gezet!r} in plaats van '4242'. "
        "Zonder een gezette waarde bewijst de rest van deze test niets."
    )
    assert eerste_pid == tweede_pid, (
        f"De twee sessies kregen verschillende verbindingen ({eerste_pid} en {tweede_pid}) "
        "terwijl de pool op een verbinding staat. Dan toetst deze test geen hergebruik en "
        "is de uitkomst hieronder betekenisloos."
    )
    assert zonder_tenant in ("", None), (
        f"Een sessie zonder tenant in de ContextVar kreeg app.current_tenant = "
        f"{zonder_tenant!r} op DEZELFDE verbinding (pid {tweede_pid}) waarop het vorige "
        "verzoek tenant 4242 zette. Onder een applicatierol is dat een cross-tenant lek, "
        "geen ongemak."
    )
