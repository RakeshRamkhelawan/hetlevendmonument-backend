"""Prana-keten: twee gelijktijdige afschrijvingen voor dezelfde klant en afdeling (meting).

Bundel logboekketens (brief 2026-10-22, uitbreiding 2026-10-23, punt 6). De vraag: een fork van
de keten wordt geweigerd door `uq_prana_tx_seq`, maar `PranaService` herhaalt niet bij een
conflict. Gaat er dan een afschrijving verloren, komt er een fout bij de gebruiker, of wordt er
herhaald?

Uitkomst van de meting: het gebeurt niet. `charge`, `refund` en `allocate_emergency` doen
EERST een UPDATE op de budgetrij van (klant, afdeling); die rijvergrendeling wacht tot de
transactie van de andere schrijver klaar is en wordt pas daarna toegekend (READ COMMITTED
leest de rij opnieuw). De staartlezing en de toevoeging staan in dezelfde transactie, dus de
tweede schrijver ziet de commit van de eerste. Er komt nooit een conflict op `uq_prana_tx_seq`
en dus is een herhaling niet nodig. Deze test legt dat vast, zodat een wijziging die de UPDATE
uit de volgorde haalt (bijvoorbeeld de staart eerst lezen) rood wordt in plaats van stil een
afschrijving te verliezen.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.governance.models import PranaDepartmentBudget, PranaTransaction
from src.core.governance.prana_hash import compute_prana_hash
from src.core.governance.prana_service import PranaService
from src.core.models.rbac_models import Tenant

TENANT_PRANA = 910_301
AFDELING = "finance"
ANDERE_AFDELING = "hr"
ACTIE = "copilot.chat"
KOSTEN = 10  # tier `ml`, zie prana_costs


@pytest.fixture
def sessiefabriek(postgres_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)


async def _opruimen(fabriek: async_sessionmaker[AsyncSession]) -> None:
    # De tenant weg: de budgetten en de transacties gaan mee (vreemde sleutel met CASCADE).
    async with fabriek() as sessie:
        await sessie.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": TENANT_PRANA})
        await sessie.commit()


@pytest_asyncio.fixture
async def prana_klant(
    sessiefabriek: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    await _opruimen(sessiefabriek)
    async with sessiefabriek() as sessie:
        sessie.add(
            Tenant(
                id=TENANT_PRANA,
                name="Prana-keten",
                slug=f"prana-keten-{TENANT_PRANA}",
                prana_budget=1_000_000,
                prana_spent=0,
            )
        )
        await sessie.commit()
    async with sessiefabriek() as sessie:
        await PranaService(sessie).provision_tenant(TENANT_PRANA)
        await sessie.commit()
    yield
    await _opruimen(sessiefabriek)


async def _transactie(
    fabriek: async_sessionmaker[AsyncSession], soort: str, afdeling: str = AFDELING
) -> None:
    """Een bewerking zoals de applicatie hem doet: eigen sessie, een transactie, commit."""
    async with fabriek() as sessie:
        service = PranaService(sessie)
        if soort == "charge":
            await service.charge(TENANT_PRANA, afdeling, ACTIE)
        elif soort == "refund":
            await service.refund(TENANT_PRANA, afdeling, ACTIE)
        else:
            await service.allocate_emergency(TENANT_PRANA, afdeling, 5, 1, "meting")
        await sessie.commit()


async def _keten(
    fabriek: async_sessionmaker[AsyncSession], afdeling: str
) -> list[PranaTransaction]:
    async with fabriek() as sessie:
        uit = await sessie.execute(
            select(PranaTransaction)
            .where(
                PranaTransaction.tenant_id == TENANT_PRANA,
                PranaTransaction.department == afdeling,
            )
            .order_by(PranaTransaction.sequence_no.asc())
        )
        return list(uit.scalars().all())


def _controleer_keten(rijen: list[PranaTransaction]) -> None:
    assert [r.sequence_no for r in rijen] == list(range(1, len(rijen) + 1)), (
        "gat of dubbel volgnummer"
    )
    for i, rij in enumerate(rijen):
        verwacht_vorige = None if i == 0 else rijen[i - 1].hash
        assert rij.previous_hash == verwacht_vorige, (
            f"keten gebroken bij volgnummer {rij.sequence_no}"
        )
        opnieuw = compute_prana_hash(
            tenant_id=rij.tenant_id,
            department=rij.department,
            action_type=rij.action_type,
            cost=rij.cost,
            kind=rij.kind,
            actor_user_id=rij.actor_user_id,
            balance_after=rij.balance_after,
            created_at=rij.created_at.isoformat(),
            previous_hash=rij.previous_hash,
        )
        assert opnieuw == rij.hash, f"hash klopt niet bij volgnummer {rij.sequence_no}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gelijktijdige_afschrijvingen_raken_geen_afschrijving_kwijt(
    sessiefabriek: async_sessionmaker[AsyncSession], prana_klant: None
) -> None:
    aantal = 12
    uitkomsten = await asyncio.gather(
        *(_transactie(sessiefabriek, "charge") for _ in range(aantal)), return_exceptions=True
    )

    fouten = [u for u in uitkomsten if isinstance(u, BaseException)]
    assert not fouten, f"{len(fouten)} afschrijvingen gaven een fout bij de aanroeper: {fouten[:2]}"

    rijen = await _keten(sessiefabriek, AFDELING)
    assert len(rijen) == 1 + aantal, "een afschrijving is verloren gegaan (1 aanvangsregel erbij)"
    _controleer_keten(rijen)
    assert sum(1 for r in rijen if r.kind == "spend") == aantal

    async with sessiefabriek() as sessie:
        budget = (
            await sessie.execute(
                select(PranaDepartmentBudget).where(
                    PranaDepartmentBudget.tenant_id == TENANT_PRANA,
                    PranaDepartmentBudget.department == AFDELING,
                )
            )
        ).scalar_one()
    assert budget.spent_prana == aantal * KOSTEN, "de teller klopt niet met de ketenregels"
    assert rijen[-1].balance_after == budget.total_prana - budget.spent_prana


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gemengde_gelijktijdige_bewerkingen_en_twee_afdelingen(
    sessiefabriek: async_sessionmaker[AsyncSession], prana_klant: None
) -> None:
    werk: list[tuple[str, str]] = (
        [("charge", AFDELING)] * 6
        + [("refund", AFDELING)] * 3
        + [("emergency", AFDELING)] * 2
        + [("charge", ANDERE_AFDELING)] * 5
    )
    uitkomsten = await asyncio.gather(
        *(_transactie(sessiefabriek, soort, afd) for soort, afd in werk), return_exceptions=True
    )

    fouten = [u for u in uitkomsten if isinstance(u, BaseException)]
    assert not fouten, f"{len(fouten)} bewerkingen gaven een fout: {fouten[:2]}"

    eerste = await _keten(sessiefabriek, AFDELING)
    tweede = await _keten(sessiefabriek, ANDERE_AFDELING)
    assert len(eerste) == 1 + 6 + 3 + 2
    assert len(tweede) == 1 + 5
    _controleer_keten(eerste)
    _controleer_keten(tweede)
