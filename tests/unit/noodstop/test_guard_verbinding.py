"""Hoe de noodstopcontrole aan een database-verbinding komt (Gate 2, punt 3).

Eerst bouwde elke controle een eigen poolloze engine (gemeten ~109 ms mediaan, 206 ms max, en een
extra verbinding per actie; bij uitputting weigerde alles voor iedereen). Nu:

- in een requestcontext (of elke loop zonder eigen run) deelt een loop EEN engine met een kleine,
  eigen pool, los van de pool van de applicatie;
- in een actor-run (`draai_in_eigen_loop`) hergebruikt de controle de engine van die run, achter een
  semafoor, zodat een run nooit meer dan een paar controles tegelijk een verbinding laat openen.

De databasegrens (`_lees_met_engine`) is vervangen; de keuze van de engine en de semafoor draaien echt.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.database.database import db_manager
from src.core.noodstop import guard

pytestmark = pytest.mark.noodstop_echt


def _nep_engine() -> MagicMock:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Telt hoeveel engines worden gebouwd en welke engine elke lezing kreeg."""
    staat: dict[str, Any] = {"klein": [], "poolloos": [], "gebruikt": []}

    def klein(**kw: Any) -> MagicMock:
        staat["klein"].append(kw)
        return _nep_engine()

    def poolloos() -> MagicMock:
        staat["poolloos"].append(1)
        return _nep_engine()

    async def lees(engine: Any, tenant_id: int) -> bool:
        staat["gebruikt"].append(engine)
        return False

    monkeypatch.setattr(db_manager, "create_small_pool_engine", klein)
    monkeypatch.setattr(db_manager, "create_poolless_engine", poolloos)
    monkeypatch.setattr(guard, "_lees_met_engine", lees)
    guard._engines_per_loop.clear()
    return staat


@pytest.mark.asyncio
async def test_in_een_requestcontext_deelt_een_loop_een_engine_met_een_kleine_pool(
    engines: dict[str, Any],
) -> None:
    for _ in range(25):
        assert await guard._lees_uit_database(1) is False
    assert len(engines["klein"]) == 1
    assert engines["poolloos"] == []
    assert len({id(e) for e in engines["gebruikt"]}) == 1
    pool = engines["klein"][0]
    assert 1 <= pool["pool_size"] <= 5
    assert pool["max_overflow"] <= 5
    assert pool["pool_timeout"] <= 5  # uitputting geeft snel een fout, geen wachtrij van 30 s


def test_een_tweede_loop_krijgt_een_eigen_engine(engines: dict[str, Any]) -> None:
    async def lees() -> None:
        await guard._lees_uit_database(1)

    asyncio.run(lees())
    asyncio.run(lees())
    assert len(engines["klein"]) == 2
    assert engines["poolloos"] == []


@pytest.mark.asyncio
async def test_in_een_actor_run_hergebruikt_de_controle_de_engine_van_de_run(
    engines: dict[str, Any],
) -> None:
    run_engine = _nep_engine()
    with guard.gebruik_eigen_run_engine(run_engine):
        for _ in range(10):
            await guard._lees_uit_database(1)
    assert engines["gebruikt"] == [run_engine] * 10
    assert engines["klein"] == [] and engines["poolloos"] == []


@pytest.mark.asyncio
async def test_in_een_actor_run_zijn_gelijktijdige_controles_begrensd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actief = 0
    hoogste = 0

    async def lees(engine: Any, tenant_id: int) -> bool:
        nonlocal actief, hoogste
        actief += 1
        hoogste = max(hoogste, actief)
        await asyncio.sleep(0.01)
        actief -= 1
        return False

    monkeypatch.setattr(guard, "_lees_met_engine", lees)
    with guard.gebruik_eigen_run_engine(_nep_engine()):
        await asyncio.gather(*(guard._lees_uit_database(1) for _ in range(30)))
    assert 2 <= hoogste <= guard.MAX_GELIJKTIJDIG_IN_EEN_RUN


def test_draai_in_eigen_loop_stelt_zijn_engine_ter_beschikking_aan_de_controle(
    engines: dict[str, Any],
) -> None:
    from src.core.tasks.eigen_loop import draai_in_eigen_loop

    gezien: list[Any] = []

    async def taak(fabriek: Any) -> None:
        await guard._lees_uit_database(1)
        gezien.extend(engines["gebruikt"])

    draai_in_eigen_loop(taak)
    assert len(engines["poolloos"]) == 1  # alleen de engine van de run zelf
    assert engines["klein"] == []
    assert len(gezien) == 1


def test_na_een_run_is_de_engine_van_de_run_niet_meer_zichtbaar() -> None:
    assert guard._eigen_run.get() is None
