"""De toolbroker houdt zijn logboek bij onder gelijktijdige last (F7, poolmeting voor de regie).

Het logboek wordt per auditregel op een EIGEN korte sessie uit de pool geschreven, en elke schrijfactie
houdt een verbinding vast terwijl hij op het adviessleutelslot van zijn klant wacht
(`pg_advisory_xact_lock`, ruimte 7201). Twintig gelijktijdige toolaanroepen kunnen dus twintig
verbindingen tegelijk vragen. Een vastgelopen pool raakt de klant direct; deze test meet dat tegen een
echte PostgreSQL met de poolwaarden die de applicatie echt gebruikt.

Poolwaarden, uit de code gehaald en niet verzonnen:

- `UnifiedConfig.database_pool_size` en `database_max_overflow` (src/core/config/unified_config.py:158-159):
  de standaardwaarden van de motor die `db_manager.get_session` gebruikt, dus ook van elke
  `audit_session_factory`. `pool_timeout` is daar vastgezet op 30 s (unified_config.py:744).
- `DatabaseConfig` in src/core/config/production_config.py:57-60: een kleinere pool (5 / 10 / 5 s). Dat is
  de strengste waarde in de code en dient hier als stresspool.

Geslaagd = geen pool-timeout, alle aanroepen slagen, precies evenveel auditregels als aanroepen en een
geldige keten per klant (geen splitsing, geen gat).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config.production_config import DatabaseConfig
from src.core.config.unified_config import UnifiedConfig
from src.core.governance.models import ToolAuditLog
from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker import service as service_module
from src.core.tool_broker.audit_repository import ToolAuditRepository
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.service import ToolBrokerService
from tests.fixtures.testdatabase import testdatabase_url

TENANT_A = 910_401
TENANT_B = 910_402
ALLE = (TENANT_A, TENANT_B)
AANTAL = 20


@dataclass(frozen=True)
class PoolWaarden:
    naam: str
    pool_size: int
    max_overflow: int
    pool_timeout: int


_UNIFIED = UnifiedConfig.model_fields
PRODUCTIEPOOL = PoolWaarden(
    "applicatiemotor",
    cast(int, _UNIFIED["database_pool_size"].default),
    cast(int, _UNIFIED["database_max_overflow"].default),
    30,
)
_KLEIN = DatabaseConfig(url="")
STRESSPOOL = PoolWaarden("kleine pool", _KLEIN.pool_size, _KLEIN.max_overflow, _KLEIN.pool_timeout)


class _Client:
    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


class _Toestemming:
    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        return True


class _PoolFouten(logging.Handler):
    """Telt logregels over een pool-timeout; `best_effort` slikt die fout, dus zonder dit zie je hem niet."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.aantal = 0

    def emit(self, record: logging.LogRecord) -> None:
        tekst = record.getMessage() + repr(record.exc_info)
        if "QueuePool" in tekst or "TimeoutError" in tekst or "timed out" in tekst:
            self.aantal += 1


@pytest.fixture(autouse=True)
def _schone_context() -> Iterator[None]:
    set_tenant_id(None)
    yield
    set_tenant_id(None)


@pytest.fixture
def pool_fouten() -> Iterator[_PoolFouten]:
    handler = _PoolFouten()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)


@pytest_asyncio.fixture
async def beheer(
    postgres_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Een gewone (poolloze) sessiefabriek voor opruimen en nameten, los van de pool die gemeten wordt."""
    fabriek = async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)

    async def _wis() -> None:
        async with fabriek() as sessie:
            await sessie.execute(delete(ToolAuditLog).where(ToolAuditLog.tenant_id.in_(ALLE)))
            await sessie.commit()

    await _wis()
    yield fabriek
    await _wis()


async def _maak_engine(waarden: PoolWaarden) -> AsyncEngine:
    return create_async_engine(
        testdatabase_url(database="sanskritisetu"),
        pool_size=waarden.pool_size,
        max_overflow=waarden.max_overflow,
        pool_timeout=waarden.pool_timeout,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def _broker(fabriek: async_sessionmaker[AsyncSession]) -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=cast(Any, _Client()),
        seq_thinking_client=cast(Any, _Client()),
        local_registry=LocalToolRegistry(),
        enable_resilience=False,
        permission_manager=cast(ToolPermissionManager, _Toestemming()),
        audit_session_factory=lambda: fabriek(),
    )


async def _wacht_op_achtergrondtaken() -> None:
    """Wacht tot elke achtergrondtaak die een auditregel schrijft klaar is (de set loopt zichzelf leeg)."""
    einde = time.monotonic() + 120
    while service_module._AUDIT_TASKS and time.monotonic() < einde:
        await asyncio.gather(*list(service_module._AUDIT_TASKS), return_exceptions=True)
    assert not service_module._AUDIT_TASKS, "er lopen na 120 s nog auditschrijvers"


async def _meet_piek(pool: Any, stop: asyncio.Event, uit: dict[str, int]) -> None:
    while not stop.is_set():
        uit["piek"] = max(uit["piek"], int(pool.checkedout()))
        await asyncio.sleep(0.002)


async def _meet(
    waarden: PoolWaarden,
    tenants: list[int],
    *,
    verzoek_houdt_sessie_vast: bool,
    beheer: async_sessionmaker[AsyncSession],
    pool_fouten: _PoolFouten,
) -> None:
    engine = await _maak_engine(waarden)
    fabriek = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    broker = _broker(fabriek)
    pool = engine.sync_engine.pool
    metingen = {"piek": 0}
    stop = asyncio.Event()
    meter = asyncio.create_task(_meet_piek(pool, stop, metingen))
    pool_fouten.aantal = 0

    async def _aanroep(nr: int) -> object:
        tenant = tenants[nr % len(tenants)]
        context: dict[str, object] = {"tenant_id": tenant}
        if not verzoek_houdt_sessie_vast:
            return await broker.execute_tool(
                "test__echo", {"message": f"m{nr}"}, agent_id="agent-last", context=context
            )
        # Zoals `get_service` per verzoek: het verzoek houdt zelf een sessie vast zolang de aanroep loopt.
        async with fabriek() as verzoeksessie:
            await verzoeksessie.execute(text("SELECT 1"))
            return await broker.execute_tool(
                "test__echo", {"message": f"m{nr}"}, agent_id="agent-last", context=context
            )

    start = time.monotonic()
    try:
        uitkomsten = await asyncio.gather(
            *(_aanroep(i) for i in range(AANTAL)), return_exceptions=True
        )
        duur_aanroepen = time.monotonic() - start
        await _wacht_op_achtergrondtaken()
        duur_totaal = time.monotonic() - start
    finally:
        stop.set()
        await meter
        await engine.dispose()

    mislukt = [u for u in uitkomsten if isinstance(u, BaseException)]
    regels: dict[int, list[ToolAuditLog]] = {}
    async with beheer() as sessie:
        for tenant in tenants:
            uit = await sessie.execute(
                select(ToolAuditLog)
                .where(ToolAuditLog.tenant_id == tenant)
                .order_by(ToolAuditLog.timestamp.asc(), ToolAuditLog.id.asc())
            )
            regels[tenant] = list(uit.scalars().all())
        totaal = sum(len(r) for r in regels.values())
        ketens = {
            tenant: await ToolAuditRepository(sessie, tenant).verify_chain_integrity()
            for tenant in tenants
        }

    # Geen aanname "pool-timeout": de meting staat in de melding, zodat een rode test zijn eigen cijfers geeft.
    samenvatting = (
        f"pool={waarden.naam} {waarden.pool_size}/{waarden.max_overflow}/{waarden.pool_timeout}s "
        f"klanten={len(tenants)} vasthoudend={verzoek_houdt_sessie_vast}: "
        f"geslaagd={AANTAL - len(mislukt)}/{AANTAL} auditregels={totaal} ketens={ketens} "
        f"piek_uitgecheckt={metingen['piek']} pooltimeouts={pool_fouten.aantal} "
        f"duur_aanroepen={duur_aanroepen:.2f}s duur_totaal={duur_totaal:.2f}s"
    )
    print("POOLMETING " + samenvatting)

    assert not mislukt, f"toolaanroepen mislukt ({samenvatting}): {mislukt[:3]!r}"
    assert pool_fouten.aantal == 0, f"pool-timeouts of QueuePool-fouten ({samenvatting})"
    assert totaal == AANTAL, f"verwacht {AANTAL} auditregels ({samenvatting})"
    assert all(ketens.values()), f"keten niet geldig ({samenvatting})"
    for tenant in tenants:
        verwacht = sum(1 for i in range(AANTAL) if tenants[i % len(tenants)] == tenant)
        assert len(regels[tenant]) == verwacht, (
            f"klant {tenant}: {len(regels[tenant])} i.p.v. {verwacht}"
        )
        assert len({r.previous_hash for r in regels[tenant]}) == len(regels[tenant]), (
            f"klant {tenant}: de keten is gesplitst (dubbele previous_hash)"
        )
        assert regels[tenant][0].previous_hash in (None, "genesis")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "tenants", [[TENANT_A], [TENANT_A, TENANT_B]], ids=["een_klant", "twee_klanten"]
)
@pytest.mark.parametrize(
    "waarden", [PRODUCTIEPOOL, STRESSPOOL], ids=lambda w: w.naam.replace(" ", "_")
)
async def test_twintig_gelijktijdige_aanroepen_houden_de_pool_niet_vast(
    waarden: PoolWaarden,
    tenants: list[int],
    beheer: async_sessionmaker[AsyncSession],
    pool_fouten: _PoolFouten,
) -> None:
    await _meet(
        waarden, tenants, verzoek_houdt_sessie_vast=False, beheer=beheer, pool_fouten=pool_fouten
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "tenants", [[TENANT_A], [TENANT_A, TENANT_B]], ids=["een_klant", "twee_klanten"]
)
async def test_twintig_aanroepen_terwijl_elk_verzoek_zelf_een_sessie_vasthoudt(
    tenants: list[int],
    beheer: async_sessionmaker[AsyncSession],
    pool_fouten: _PoolFouten,
) -> None:
    """Zoals in productie: elk verzoek houdt een sessie vast en de broker vraagt er daarnaast een voor het logboek.

    Alleen de productiepool: bij de kleine pool (15 verbindingen) putten twintig verzoeken de pool al uit
    zonder dat het logboek meedoet, en dan meet je het verzoek en niet het logboek.
    """
    await _meet(
        PRODUCTIEPOOL,
        tenants,
        verzoek_houdt_sessie_vast=True,
        beheer=beheer,
        pool_fouten=pool_fouten,
    )
