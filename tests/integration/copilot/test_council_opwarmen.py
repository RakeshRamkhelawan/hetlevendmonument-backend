"""De council wordt bij het opstarten opgewarmd, zodat de eerste klant de koude kosten niet draagt (2026-10-23).

Gemeten (productie-`build_council`, vers proces, lokale testdatabase, twee runs per variant): alleen de RiskOfficer is bij zijn
eerste aanroep traag, 128 tot 360 ms tegen 5 tot 15 ms warm. Voorverwarmen met een kale `select 1` liet hem op 105-121 ms staan;
voorverwarmen met de echte registerquery (`actor_track_record`) bracht hem op 8-13 ms. De koude kosten zijn dus de eerste
verbinding PLUS de eerste uitvoering van die ene query (statement bouwen). Het beleid (`policies/default.yaml`) geeft hem 500 ms.

Wat deze tests vastleggen:
1. na `warm_up_risk_register` bouwt de eerste echte registerquery GEEN nieuw statement meer in de cache van de engine
   (deterministisch, geen tijdmeting: die is op een belaste machine niet stabiel);
2. de opwarming is niet-fataal: een kapotte database stopt het opstarten niet;
3. de lifespan roept de opwarming aan.

Mutatiebewijs (wegwerp-worktree): `warm_up_risk_register` een lege functie maken laat test 1 rood worden; de stap uit `init_steps`
halen laat test 3 rood worden; de `except` weghalen laat test 2 rood worden.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from tests.fixtures.testdatabase import testdatabase_url

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_na_het_opwarmen_bouwt_de_eerste_registerquery_geen_nieuw_statement() -> None:
    from src.core.copilot.council.factory import _RiskRegisterAdapter, warm_up_risk_register
    from src.core.database.tenant_query_filter import init_tenant_auto_filtering
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

    engine = create_async_engine(testdatabase_url())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    # Zoals in productie: `_init_tenant_filtering` is de eerste lifespan-stap, VOOR de opwarming. De listener hangt aan de
    # Session-klasse; hij wordt daarom aan het eind weer verwijderd (ADR-036 OP-20).
    listener = init_tenant_auto_filtering()
    try:
        await warm_up_risk_register(maker)
        voor = len(engine.sync_engine._compiled_cache)  # type: ignore[arg-type]

        set_tenant_id(1)
        async with maker() as sessie:
            await _RiskRegisterAdapter(sessie).actor_track_record(1, "send_notification")
        na = len(engine.sync_engine._compiled_cache)  # type: ignore[arg-type]
    finally:
        event.remove(Session, "do_orm_execute", listener)
        clear_tenant_context()
        await engine.dispose()

    assert na == voor, (
        f"de eerste echte registerquery bouwde {na - voor} nieuw(e) statement(s); "
        "de opwarming gebruikt dus niet dezelfde query"
    )


@pytest.mark.asyncio
async def test_een_kapotte_database_stopt_het_opstarten_niet() -> None:
    from src.core.copilot.council.factory import warm_up_risk_register

    def kapotte_fabriek() -> object:
        raise ConnectionRefusedError("database is er niet")

    gelukt = await warm_up_risk_register(kapotte_fabriek)  # type: ignore[arg-type]

    assert gelukt is False


def test_de_lifespan_roept_de_opwarming_aan() -> None:
    boom = ast.parse((REPO / "src" / "core" / "app_lifespan.py").read_text(encoding="utf-8"))
    stapnamen = {
        knoop.value
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str)
    }

    assert "_init_council_warmup" in stapnamen


@pytest.mark.asyncio
async def test_een_hangende_database_houdt_het_opstarten_niet_vast() -> None:
    """Security-review Gate 2 (2026-10-23): zonder tijdsgrens blokkeert een niet-reagerende pool de hele lifespan."""
    import asyncio

    from src.core.copilot.council.factory import warm_up_risk_register

    class _Hangt:
        async def __aenter__(self) -> object:
            await asyncio.sleep(3600)
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    gelukt = await asyncio.wait_for(
        warm_up_risk_register(lambda: _Hangt(), timeout_seconds=0.2),  # type: ignore[arg-type]
        timeout=5,
    )

    assert gelukt is False


@pytest.mark.asyncio
@pytest.mark.parametrize("breekt", [True, False])
async def test_de_opwarming_herstelt_de_tenantcontext_die_er_al_was(breekt: bool) -> None:
    from src.core.copilot.council.factory import warm_up_risk_register
    from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id, set_tenant_id

    class _Leeg:
        async def __aenter__(self) -> object:
            if breekt:
                raise ConnectionRefusedError("weg")
            raise RuntimeError("geen sessie nodig voor deze test")

        async def __aexit__(self, *args: object) -> None:
            return None

    set_tenant_id(7)
    try:
        await warm_up_risk_register(lambda: _Leeg())  # type: ignore[arg-type]
        daarna = get_tenant_id()
    finally:
        clear_tenant_context()

    assert daarna == 7


@pytest.mark.asyncio
async def test_de_opwarming_opent_meer_verbindingen_tegelijk() -> None:
    """Gemeten 2026-10-23 in de volle stack: een nieuwe verbinding naar `localhost` kost 2,1 s (Windows probeert eerst IPv6 en wacht
    op de weigering), naar 127.0.0.1 50-66 ms. Een voorstel gebruikt meerdere sessies tegelijk; met een pool met een verbinding
    betaalt het eerste voorstel de rest. De opwarming opent er daarom een paar tegelijk."""
    import asyncio

    from src.core.copilot.council.factory import warm_up_risk_register

    actief = 0
    hoogste = 0

    class _Sessie:
        async def __aenter__(self) -> object:
            nonlocal actief, hoogste
            actief += 1
            hoogste = max(hoogste, actief)
            await asyncio.sleep(0.05)
            raise RuntimeError("geen echte sessie nodig")

        async def __aexit__(self, *args: object) -> None:
            nonlocal actief
            actief -= 1

    await warm_up_risk_register(lambda: _Sessie(), verbindingen=3)  # type: ignore[arg-type]

    assert hoogste == 3


@pytest.mark.asyncio
async def test_een_geannuleerde_opwarmsessie_laat_het_opstarten_niet_crashen() -> None:
    """Security-review Gate 2 ronde 2 (2026-10-23): `gather(return_exceptions=True)` geeft een geannuleerde kindtaak terug als
    CancelledError-instantie; dat is geen Exception meer (Python 3.8+) en glipte langs `except Exception`, tot in de lifespan."""
    import asyncio

    from src.core.copilot.council.factory import warm_up_risk_register

    class _Geannuleerd:
        async def __aenter__(self) -> object:
            raise asyncio.CancelledError()

        async def __aexit__(self, *args: object) -> None:
            return None

    gelukt = await warm_up_risk_register(lambda: _Geannuleerd(), verbindingen=2)  # type: ignore[arg-type]

    assert gelukt is False
