"""Twee gelijktijdige runs van `verstuur_klare_berichten` versturen een bericht EEN keer.

Keten B dag 2, `test_bericht_niet_twee_keer_verzonden` in zijn gelijktijdige vorm. Dit is een
integratietest tegen echte PostgreSQL (netwerkpoort 5455) omdat de bescherming een rijslot of een
atomaire claim is (`SELECT ... FOR UPDATE SKIP LOCKED`, of een `UPDATE ... WHERE status = 'klaar'
RETURNING`). SQLite kent geen rijsloten en serialiseert schrijvers, dus daar is deze race niet te
meten; de sequentiele vorm staat in `tests/unit/debiteuren/test_verzenden.py`.

**Opstelling.** Elke run krijgt een EIGEN sessie op een EIGEN verbinding (twee workers), via de
seam `sessie_fabriek` van de kern. De SMTP-dubbel (`aiosmtplib.send`) wacht 0,3 s per brief, zodat
beide runs elkaar echt overlappen: een implementatie die eerst leest, dan verstuurt en daarna pas
`verzonden` schrijft, verstuurt hier dubbel. De rijen worden ECHT gecommit en na afloop weer
verwijderd (de moduleopruiming van `reset_db_per_module` ruimt de rest).

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py` en `tests/integration/
conftest.py`: `enforce_testing_env`, `_reset_global_state`, `ensure_main_thread_event_loop`,
`_seed_module_snapshot`, `reset_db_per_module` (TRUNCATE + seed per module). Geen daarvan raakt
mail, rijsloten of de berichten.

**Mutatie die dit moet betrappen.** De implementatie leest alle `klaar`-rijen zonder slot of
claim en schrijft `verzonden` pas na het versturen: dan ontvangt de SMTP-dubbel twee brieven.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.models.outgoing_message_models import OutgoingMessage
from tests.unit.debiteuren._smtp_dubbel import installeer_smtp_dubbel, zet_testmailbox

TENANT_ID = 1


def _eigen_sessies(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        async with maker() as sessie:
            yield sessie

    return _sessie


async def _draai(fabriek: Callable[[], AbstractAsyncContextManager[AsyncSession]]) -> None:
    from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

    await verstuur_klare_berichten_async(sessie_fabriek=fabriek)


async def _zet_berichten(engine: AsyncEngine, aantal: int) -> list[int]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as sessie:
        rijen = [
            OutgoingMessage(
                tenant_id=TENANT_ID,
                channel="email",
                kind="herinnering",
                recipient=f"debiteur{i}@klant.example",
                subject=f"Herinnering {i}",
                body=f"Tekst {i}",
                status="klaar",
            )
            for i in range(aantal)
        ]
        sessie.add_all(rijen)
        await sessie.commit()
        return [r.id for r in rijen]


async def _ruim_op(engine: AsyncEngine, ids: list[int]) -> None:
    async with async_sessionmaker(engine)() as sessie:
        await sessie.execute(delete(OutgoingMessage).where(OutgoingMessage.id.in_(ids)))
        await sessie.commit()


async def _statussen(engine: AsyncEngine, ids: list[int]) -> list[str]:
    async with async_sessionmaker(engine)() as sessie:
        rijen = await sessie.execute(
            select(OutgoingMessage.status)
            .where(OutgoingMessage.id.in_(ids))
            .order_by(OutgoingMessage.id)
        )
        return list(rijen.scalars().all())


@pytest.mark.integration
@pytest.mark.asyncio
class TestGelijktijdigeRuns:
    async def test_twee_gelijktijdige_runs_versturen_een_bericht_een_keer(
        self, postgres_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        dubbel.vertraging = 0.3
        ids = await _zet_berichten(postgres_engine, 1)
        try:
            await asyncio.gather(
                _draai(_eigen_sessies(postgres_engine)), _draai(_eigen_sessies(postgres_engine))
            )
        finally:
            statussen = await _statussen(postgres_engine, ids)
            await _ruim_op(postgres_engine, ids)

        assert (len(dubbel.ontvangen), statussen) == (1, ["verzonden"])

    async def test_met_meerdere_berichten_gaat_elk_bericht_precies_een_keer(
        self, postgres_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        dubbel.vertraging = 0.1
        ids = await _zet_berichten(postgres_engine, 5)
        try:
            await asyncio.gather(
                _draai(_eigen_sessies(postgres_engine)), _draai(_eigen_sessies(postgres_engine))
            )
        finally:
            statussen = await _statussen(postgres_engine, ids)
            await _ruim_op(postgres_engine, ids)

        ontvangers = sorted(b.ontvanger for b in dubbel.ontvangen)
        assert ontvangers == sorted(f"debiteur{i}@klant.example" for i in range(5))
        assert statussen == ["verzonden"] * 5

    async def test_een_enkele_run_op_postgres_verstuurt_wel(
        self, postgres_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Andere kant op: "nooit versturen" is geen geldige manier om dubbel te voorkomen."""
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        ids = await _zet_berichten(postgres_engine, 1)
        try:
            await _draai(_eigen_sessies(postgres_engine))
        finally:
            statussen = await _statussen(postgres_engine, ids)
            await _ruim_op(postgres_engine, ids)

        assert (len(dubbel.ontvangen), statussen) == (1, ["verzonden"])
