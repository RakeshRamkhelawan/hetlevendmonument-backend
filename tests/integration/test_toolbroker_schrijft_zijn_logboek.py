"""De toolbroker schrijft zijn eigen logboek (ADR-019) -- F7, brief 2026-10-25.

`ToolBrokerService` schreef alleen met een `audit_repository` plus `db_session`, en geen enkele plek
die de broker bouwde gaf die mee: in productie kwam er nooit een regel in `tool_audit_logs`. Nu geeft
elke maker een `audit_session_factory` mee, en de broker bouwt per regel een repository voor de klant
van DEZE aanroep, op een eigen korte sessie.

Wat hier rood moest zijn voor de fix en nu groen is, tegen een echte PostgreSQL:

- een toolaanroep (geslaagd en geweigerd) geeft een ketenregel voor die klant;
- de regel bevat geen geheim uit `tool_input`;
- een falende logboekschrijving laat de toolaanroep zelf slagen (best effort);
- klant B ziet de regels van klant A niet, en een aan klant A gebonden repository schrijft niets
  voor een aanroep van klant B.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.governance.models import ToolAuditLog
from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
from src.core.tool_broker.audit_repository import ToolAuditRepository
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.service import ToolBrokerService

TENANT_A = 910_301
TENANT_B = 910_302
TENANT_GEBONDEN = 910_303
GEHEIM = "S3cret-WACHTWOORD-q9x7"
ALLE = (TENANT_A, TENANT_B, TENANT_GEBONDEN)


class _Client:
    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


class _Toestemming:
    """Een permissiemanager die alles toestaat of alles weigert; de redenering zelf is hier niet de toets."""

    def __init__(self, toegestaan: bool) -> None:
        self._toegestaan = toegestaan

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        return self._toegestaan


@pytest.fixture(autouse=True)
def _schone_context() -> Iterator[None]:
    set_tenant_id(None)
    yield
    set_tenant_id(None)


@pytest.fixture
def fabriek(postgres_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)


async def _wis(fabriek: async_sessionmaker[AsyncSession]) -> None:
    async with fabriek() as sessie:
        await sessie.execute(delete(ToolAuditLog).where(ToolAuditLog.tenant_id.in_(ALLE)))
        await sessie.commit()


@pytest_asyncio.fixture
async def schoon(fabriek: async_sessionmaker[AsyncSession]) -> AsyncGenerator[None, None]:
    await _wis(fabriek)
    yield
    await _wis(fabriek)


def _broker(
    fabriek: async_sessionmaker[AsyncSession] | None,
    *,
    toegestaan: bool = True,
    **extra: Any,
) -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=cast(Any, _Client()),
        seq_thinking_client=cast(Any, _Client()),
        local_registry=LocalToolRegistry(),
        enable_resilience=False,
        permission_manager=cast(ToolPermissionManager, _Toestemming(toegestaan)),
        audit_session_factory=(lambda: fabriek()) if fabriek is not None else None,
        **extra,
    )


async def _regels(fabriek: async_sessionmaker[AsyncSession], tenant_id: int) -> list[ToolAuditLog]:
    async with fabriek() as sessie:
        uit = await sessie.execute(
            select(ToolAuditLog)
            .where(ToolAuditLog.tenant_id == tenant_id)
            .order_by(ToolAuditLog.timestamp.asc(), ToolAuditLog.id.asc())
        )
        return list(uit.scalars().all())


async def _wacht_op(
    fabriek: async_sessionmaker[AsyncSession], tenant_id: int, aantal: int
) -> list[ToolAuditLog]:
    """De regel van een geslaagde aanroep wordt als achtergrondtaak geschreven: even wachten."""
    regels: list[ToolAuditLog] = []
    for _ in range(100):
        regels = await _regels(fabriek, tenant_id)
        if len(regels) >= aantal:
            return regels
        await asyncio.sleep(0.05)
    return regels


async def _voer_uit(broker: ToolBrokerService, tenant_id: int, payload: dict[str, Any]) -> Any:
    return await broker.execute_tool(
        "test__echo", payload, agent_id="agent-f7", context={"tenant_id": tenant_id}
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_een_geslaagde_en_een_geweigerde_aanroep_geven_elk_een_ketenregel(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    await _voer_uit(_broker(fabriek), TENANT_A, {"message": "hallo"})
    with pytest.raises(ToolExecutionException):
        await _voer_uit(_broker(fabriek, toegestaan=False), TENANT_A, {"message": "nee"})

    regels = await _wacht_op(fabriek, TENANT_A, 2)

    assert sorted(r.status for r in regels) == ["blocked", "success"], (
        f"verwacht een geslaagde en een geweigerde regel voor de klant, gevonden "
        f"{[r.status for r in regels]}"
    )
    assert all(r.tenant_id == TENANT_A and r.agent_id == "agent-f7" for r in regels)
    assert regels[0].previous_hash in (None, "genesis"), "de eerste regel begint de keten"
    assert regels[1].previous_hash == regels[0].audit_hash, "de tweede regel hangt aan de eerste"
    async with fabriek() as sessie:
        assert await ToolAuditRepository(sessie, TENANT_A).verify_chain_integrity()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_de_ketenregel_bevat_geen_geheim_uit_tool_input(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    payload = {"password": GEHEIM, "api_key": GEHEIM, "message": f"mijn wachtwoord is {GEHEIM}"}
    await _voer_uit(_broker(fabriek), TENANT_A, dict(payload))
    with pytest.raises(ToolExecutionException):
        await _voer_uit(_broker(fabriek, toegestaan=False), TENANT_A, dict(payload))

    regels = await _wacht_op(fabriek, TENANT_A, 2)

    assert len(regels) == 2
    for regel in regels:
        alles = repr((regel.tool_input, regel.tool_output, regel.error_detail, regel.output_hash))
        assert GEHEIM not in alles, f"geheim in de {regel.status}-regel: {alles[:200]}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_een_falende_logboekschrijving_laat_de_toolaanroep_slagen(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    # (a) de sessie opent niet
    @asynccontextmanager
    async def _kapot() -> AsyncGenerator[AsyncSession, None]:
        raise RuntimeError("db weg")
        yield  # pragma: no cover

    kapot = _broker(None)
    kapot.audit_session_factory = _kapot
    uitkomst = await _voer_uit(kapot, TENANT_A, {"message": "hallo"})
    await asyncio.sleep(0.2)
    assert uitkomst, "de toolaanroep moet slagen als de sessie niet opent"

    # (b) het schrijven zelf faalt
    with patch.object(
        ToolAuditRepository, "log_execution", AsyncMock(side_effect=RuntimeError("x"))
    ):
        uitkomst = await _voer_uit(_broker(fabriek), TENANT_A, {"message": "hallo"})
        await asyncio.sleep(0.2)
        assert uitkomst, "de toolaanroep moet slagen als het schrijven faalt"
        # Een geweigerde poging houdt zijn eigen fout (de weigering), niet de logboekfout.
        with pytest.raises(ToolExecutionException) as fout:
            await _voer_uit(_broker(fabriek, toegestaan=False), TENANT_A, {"message": "x"})
        assert "Permission denied" in str(fout.value)

    assert await _regels(fabriek, TENANT_A) == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_klant_b_ziet_de_regels_van_klant_a_niet(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    broker = _broker(fabriek)
    await _voer_uit(broker, TENANT_A, {"message": "alleen-voor-a"})
    await _voer_uit(broker, TENANT_B, {"message": "alleen-voor-b"})

    a = await _wacht_op(fabriek, TENANT_A, 1)
    b = await _wacht_op(fabriek, TENANT_B, 1)

    assert len(a) == 1 and len(b) == 1
    assert a[0].tenant_id == TENANT_A and b[0].tenant_id == TENANT_B
    assert b[0].previous_hash in (None, "genesis"), "klant B heeft een EIGEN keten"
    async with fabriek() as sessie:
        gezien_door_b = await ToolAuditRepository(sessie, TENANT_B).get_logs(limit=50)
    assert [r.id for r in gezien_door_b] == [b[0].id]
    assert get_tenant_id() is None, "de tenantcontext van de aanroeper is niet teruggezet"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_een_aan_een_andere_klant_gebonden_repository_schrijft_niets(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    """Het oudere paar (`audit_repository` + `db_session`) is aan een klant gebonden."""
    async with fabriek() as sessie:
        repo = ToolAuditRepository(sessie, TENANT_GEBONDEN)
        broker = _broker(None, audit_repository=repo, db_session=sessie)
        await _voer_uit(broker, TENANT_A, {"message": "hallo"})
        await asyncio.sleep(0.3)

    assert await _regels(fabriek, TENANT_A) == []
    assert await _regels(fabriek, TENANT_GEBONDEN) == []


@pytest.mark.unit
def test_de_makers_geven_het_logboek_mee() -> None:
    """De twee makers die zonder agent of database te bouwen zijn."""
    from src.core.tool_broker.dependencies import ToolBrokerDependencies
    from src.core.tool_broker.workflow_identiteit import bouw_workflow_broker

    workflow = bouw_workflow_broker()
    assert workflow.audit_session_factory is not None and workflow._audit_actief()

    per_verzoek = ToolBrokerDependencies.get_service(db=cast(AsyncSession, AsyncMock()))
    assert per_verzoek.audit_session_factory is not None and per_verzoek._audit_actief()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_een_toolnaam_en_agent_id_van_300_tekens_geven_toch_een_regel(
    fabriek: async_sessionmaker[AsyncSession], schoon: None
) -> None:
    """S3 (Gate 2): de kolommen zijn varchar(255); een langere naam gaf geen regel (truncatiefout)."""
    lange_tool = "test__" + "t" * 294
    lange_agent = "a" * 300
    broker_geweigerd = _broker(fabriek, toegestaan=False)
    with pytest.raises(ToolExecutionException):
        await broker_geweigerd.execute_tool(
            lange_tool, {"message": "nee"}, agent_id=lange_agent, context={"tenant_id": TENANT_A}
        )
    await _voer_uit_met_agent(_broker(fabriek), TENANT_A, lange_agent)

    regels = await _wacht_op(fabriek, TENANT_A, 2)

    assert sorted(r.status for r in regels) == ["blocked", "success"]
    assert all(len(r.agent_id) <= 255 and len(r.tool_name) <= 255 for r in regels)
    async with fabriek() as sessie:
        assert await ToolAuditRepository(sessie, TENANT_A).verify_chain_integrity()


async def _voer_uit_met_agent(broker: ToolBrokerService, tenant_id: int, agent_id: str) -> object:
    return await broker.execute_tool(
        "test__echo", {"message": "hallo"}, agent_id=agent_id, context={"tenant_id": tenant_id}
    )
