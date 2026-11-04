"""Toolbroker-auditketen: gelijktijdige schrijvers voor een klant splitsen de keten niet.

Bundel logboekketens (brief 2026-10-22), vondst Gate 2 op `6b615f1b`: `ToolAuditRepository`
las de vorige hash in een APARTE aanroep (`get_last_audit_hash`, ordening alleen op
`timestamp`), zette de tijdstempel zonder slot en schreef daarna. Twee gelijktijdige
toolacties voor een klant lazen dezelfde vorige hash en SPLITSTEN de keten.

Elke schrijver krijgt hier een EIGEN sessie (zoals elke toolactie een eigen achtergrondtaak
is): met een gedeelde sessie serialiseert SQLAlchemy en bewijst de test niets.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.governance.models import ToolAuditLog
from src.core.tool_broker.audit_repository import TOOL_AUDIT_LOCK_RUIMTE, ToolAuditRepository
from src.core.tool_broker.audit_utils import compute_audit_hash

# Eigen klantnummers: `tool_audit_logs.tenant_id` heeft geen vreemde sleutel, dus een kale klant
# volstaat en geen test raakt een andere.
TENANT_GELIJKTIJDIG = 910_201
TENANT_BESTAAND = 910_202
TENANT_SLOT_A = 910_203
TENANT_SLOT_B = 910_204
TENANT_ANDERE_KETEN = 910_205
AANTAL = 22


@pytest.fixture
def sessiefabriek(postgres_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)


async def _wis(fabriek: async_sessionmaker[AsyncSession], *tenants: int) -> None:
    async with fabriek() as sessie:
        await sessie.execute(delete(ToolAuditLog).where(ToolAuditLog.tenant_id.in_(tenants)))
        await sessie.commit()


@pytest_asyncio.fixture
async def schone_klanten(
    sessiefabriek: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    alle = (
        TENANT_GELIJKTIJDIG,
        TENANT_BESTAAND,
        TENANT_SLOT_A,
        TENANT_SLOT_B,
        TENANT_ANDERE_KETEN,
    )
    await _wis(sessiefabriek, *alle)
    yield
    await _wis(sessiefabriek, *alle)


async def _schrijf(fabriek: async_sessionmaker[AsyncSession], tenant_id: int, naam: str) -> None:
    """Een toolauditregel zoals de applicatie hem schrijft: eigen sessie, eigen transactie."""
    async with fabriek() as sessie:
        repo = ToolAuditRepository(sessie, tenant_id)
        await repo.log_execution(
            agent_id="agent-ketentest",
            tool_name=f"test__{naam}",
            risk_level="low",
            tool_input={"naam": naam},
            tool_output={"ok": True},
            status="success",
            duration_seconds=0.01,
        )


async def _regels(fabriek: async_sessionmaker[AsyncSession], tenant_id: int) -> list[ToolAuditLog]:
    async with fabriek() as sessie:
        uit = await sessie.execute(
            select(ToolAuditLog)
            .where(ToolAuditLog.tenant_id == tenant_id)
            .order_by(ToolAuditLog.timestamp.asc(), ToolAuditLog.id.asc())
        )
        return list(uit.scalars().all())


async def _verifieer(fabriek: async_sessionmaker[AsyncSession], tenant_id: int) -> bool:
    async with fabriek() as sessie:
        return await ToolAuditRepository(sessie, tenant_id).verify_chain_integrity()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_twee_en_twintig_gelijktijdige_regels_geven_een_keten(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """Stap 0 van de brief: rood op de oude code, groen met het slot per klant."""
    await asyncio.gather(
        *(_schrijf(sessiefabriek, TENANT_GELIJKTIJDIG, f"gelijktijdig-{i}") for i in range(AANTAL))
    )

    regels = await _regels(sessiefabriek, TENANT_GELIJKTIJDIG)
    assert len(regels) == AANTAL, f"verwacht {AANTAL} regels, gevonden {len(regels)}"

    # Een keten: precies een kop, en elke vorige hash komt precies een keer voor. Bij een
    # SPLITSING delen twee regels dezelfde vorige hash.
    koppen = [r for r in regels if r.previous_hash in (None, "genesis")]
    assert len(koppen) == 1, f"{len(koppen)} regels beginnen een keten, verwacht 1 (gesplitst)"
    vorige = [r.previous_hash for r in regels if r.previous_hash not in (None, "genesis")]
    assert len(set(vorige)) == len(vorige), "twee regels delen dezelfde vorige hash (gesplitst)"

    assert await _verifieer(sessiefabriek, TENANT_GELIJKTIJDIG), (
        "verify_chain_integrity faalt op een keten die alleen door gelijktijdigheid is ontstaan"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_een_bestaande_keten_van_voor_de_fix_blijft_geldig(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """Rijen zoals de oude code ze schreef (hash over dezelfde velden) blijven een geldige keten."""
    begin = datetime.now(timezone.utc) - timedelta(minutes=5)
    vorige: str | None = None
    laatste_hash = ""
    async with sessiefabriek() as sessie:
        for i in range(3):
            tijd = begin + timedelta(seconds=i)
            invoer = {"oud": i}
            laatste_hash = compute_audit_hash(
                tenant_id=TENANT_BESTAAND,
                agent_id="agent-oud",
                tool_name="test__oud",
                timestamp=tijd,
                status="success",
                output_hash=None,
                previous_hash=vorige,
                tool_input=invoer,
            )
            sessie.add(
                ToolAuditLog(
                    tenant_id=TENANT_BESTAAND,
                    agent_id="agent-oud",
                    tool_name="test__oud",
                    risk_level="low",
                    tool_input=invoer,
                    status="success",
                    previous_hash=vorige,
                    audit_hash=laatste_hash,
                    timestamp=tijd,
                )
            )
            vorige = laatste_hash
        await sessie.commit()

    assert await _verifieer(sessiefabriek, TENANT_BESTAAND), (
        "de opgezette oude keten is al ongeldig"
    )

    await asyncio.gather(
        *(_schrijf(sessiefabriek, TENANT_BESTAAND, f"nieuw-{i}") for i in range(4))
    )

    regels = await _regels(sessiefabriek, TENANT_BESTAAND)
    assert len(regels) == 7
    assert regels[3].previous_hash == laatste_hash, (
        "de eerste nieuwe regel hangt niet aan de oude keten"
    )
    assert await _verifieer(sessiefabriek, TENANT_BESTAAND)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_regels_van_twee_klanten_blokkeren_elkaar_niet(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """Het slot is per klant: klant A vasthouden laat klant B ongemoeid, en A zelf wacht wel."""
    async with sessiefabriek() as houder:
        await houder.execute(
            text("SELECT pg_advisory_xact_lock(:ruimte, :tenant)"),
            {"ruimte": TOOL_AUDIT_LOCK_RUIMTE, "tenant": TENANT_SLOT_A},
        )
        # Klant B schrijft zonder te wachten.
        await asyncio.wait_for(_schrijf(sessiefabriek, TENANT_SLOT_B, "b"), timeout=10)

        # Klant A moet wachten zolang het slot vastzit: anders bewijst de rest niets.
        taak = asyncio.create_task(_schrijf(sessiefabriek, TENANT_SLOT_A, "a"))
        await asyncio.sleep(1.0)
        assert not taak.done(), "klant A schreef door terwijl zijn slot werd vastgehouden"
        await houder.rollback()

    await asyncio.wait_for(taak, timeout=10)
    assert len(await _regels(sessiefabriek, TENANT_SLOT_A)) == 1
    assert len(await _regels(sessiefabriek, TENANT_SLOT_B)) == 1
    assert await _verifieer(sessiefabriek, TENANT_SLOT_A)
    assert await _verifieer(sessiefabriek, TENANT_SLOT_B)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_de_toolketen_wacht_niet_op_het_slot_van_de_auditlogketen(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """`AuditService.log_event` sluit de `audit_logs`-keten af met de ENKELVOUDIGE sleutel (het
    klantnummer). De toolketen gebruikt de tweesleutelvorm, een andere sleutelruimte: hou het
    slot van de andere keten vast en een toolauditregel voor dezelfde klant schrijft gewoon door.
    """
    async with sessiefabriek() as houder:
        await houder.execute(
            text("SELECT pg_advisory_xact_lock(:sleutel)"), {"sleutel": TENANT_ANDERE_KETEN}
        )
        await asyncio.wait_for(_schrijf(sessiefabriek, TENANT_ANDERE_KETEN, "naast"), timeout=10)
        await houder.rollback()

    assert len(await _regels(sessiefabriek, TENANT_ANDERE_KETEN)) == 1
