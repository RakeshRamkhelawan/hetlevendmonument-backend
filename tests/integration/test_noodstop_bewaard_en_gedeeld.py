"""Noodstop per klant: de stand is bewaard en gedeeld, en de echte keten weigert (ADR-036 OP-03).

Geen vervanging van de lezer: `noodstop_echt` zet de autouse-stub uit. De stand wordt ECHT vastgelegd
(service, commit op een eigen verbinding) en daarna gelezen door de echte deur-controle op een
poolloze verbinding. Een tweede PROCES (`python -c`) staat voor een andere worker of een herstart:
het heeft geen enkel geheugen van dit proces, dus wat het ziet staat in de database.

Gemeten: klant A stilgezet, dan weigert de broker de actie van A en laat hij die van B door; een
nieuw proces ziet dezelfde stand; opheffen werkt ook in dat andere proces; zonder rij staat een klant
niet stil.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database.bypass_session import adopt_tenant
from src.core.noodstop.guard import KlantStilgezet, eis_klant_actief
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.service import ToolBrokerService
from tests.fixtures.testdatabase import testdatabase_url

KLANT_A, KLANT_B = 1, 2

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.noodstop_echt]


async def _zet(tenant_id: int, stilgezet: bool) -> None:
    """Legt de stand vast via de repository, op een EIGEN verbinding met echte commits."""
    engine = create_async_engine(testdatabase_url())
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessie:
            async with adopt_tenant(sessie, tenant_id):
                await _zet_zonder_gebruiker(sessie, tenant_id, stilgezet)
    finally:
        await engine.dispose()


async def _zet_zonder_gebruiker(sessie: AsyncSession, tenant_id: int, stilgezet: bool) -> None:
    from src.core.repositories.tenant_noodstop_repository import TenantNoodstopRepository

    await TenantNoodstopRepository(sessie).set_stand(
        tenant_id, stilgezet, reden="integratietest", user_id=None, door_platform=False
    )
    await sessie.commit()


async def _opruimen() -> None:
    engine = create_async_engine(testdatabase_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM tenant_noodstop WHERE tenant_id IN (1, 2)"))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _schoon() -> AsyncGenerator[None, None]:
    await _opruimen()
    yield
    await _opruimen()


def _ander_proces(tenant_id: int) -> str:
    """Wat een tweede proces (andere worker, of na een herstart) over deze klant vaststelt."""
    code = (
        "import asyncio, sys\n"
        "from src.core.noodstop.guard import klant_staat_stil\n"
        "print('STIL' if asyncio.run(klant_staat_stil(int(sys.argv[1]))) else 'ACTIEF')\n"
    )
    uit = subprocess.run(
        [sys.executable, "-c", code, str(tenant_id)],
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        capture_output=True,
        text=True,
        timeout=120,
        cwd=os.getcwd(),
    )
    assert uit.returncode == 0, uit.stderr[-2000:]
    return uit.stdout.strip().splitlines()[-1]


class _Client:
    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok"}


def _broker() -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=_Client(), seq_thinking_client=_Client(), enable_resilience=False
    )


async def test_zonder_rij_staat_een_klant_niet_stil() -> None:
    await eis_klant_actief(KLANT_A)


async def test_een_stilgezette_klant_wordt_geweigerd_en_een_andere_niet() -> None:
    await _zet(KLANT_A, True)
    with pytest.raises(KlantStilgezet):
        await eis_klant_actief(KLANT_A)
    await eis_klant_actief(KLANT_B)


async def test_de_broker_weigert_de_actie_van_klant_a_en_laat_die_van_klant_b_door() -> None:
    await _zet(KLANT_A, True)
    with pytest.raises(ToolExecutionException) as fout:
        await _broker().execute_tool(
            tool_name="create_task",
            payload={"title": "x"},
            agent_id="copilot",
            context={"tenant_id": KLANT_A},
        )
    assert "stilgezet" in str(fout.value.detail)
    try:
        await _broker().execute_tool(
            tool_name="create_task",
            payload={"title": "x"},
            agent_id="copilot",
            context={"tenant_id": KLANT_B},
        )
    except ToolExecutionException as stop:
        # Een ander falen (rechten, ontbrekende tool) mag; de noodstop mag het niet zijn.
        assert "stilgezet" not in str(stop.detail)


async def test_de_stand_geldt_in_een_ander_proces_en_na_opheffen_ook() -> None:
    await _zet(KLANT_A, True)
    assert _ander_proces(KLANT_A) == "STIL"
    assert _ander_proces(KLANT_B) == "ACTIEF"
    await _zet(KLANT_A, False)
    assert _ander_proces(KLANT_A) == "ACTIEF"
