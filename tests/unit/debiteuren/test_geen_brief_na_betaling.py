"""Geen brief na betaling -- debiteuren vanzelf afronden, B1 (2026-10-20).

Gemeten door de acceptant (2026-10-19): een vordering die betaald wordt gezet NA goedkeuren maar VOOR verzending
kreeg toch de brief (Mailpit +1). Nu:

1. De verzendtaak leest vlak voor het versturen opnieuw de status van de vordering, onder een rijslot
   (`SELECT ... FOR UPDATE`, dezelfde transactie). Is hij betaald (of bestaat hij niet binnen de tenant), dan wordt het
   bericht NIET verstuurd maar geannuleerd, met een auditregel in de eigen tenant.
2. "Geannuleerd" bestaat niet als status (de CHECK op `outgoing_messages.status` kent alleen klaar, verzonden en
   mislukt; een nieuwe status vraagt een migratie en de brief zegt daar STOP). Een geannuleerd bericht is daarom
   `mislukt` met `pogingen = MAX_POGINGEN` en een foutreden die met "Geannuleerd:" begint: het wordt nooit meer
   opgepakt.
3. Betaald zetten (`ReceivableRepository.update`) annuleert in dezelfde transactie een nog niet verstuurd bericht van
   die vordering; een al verzonden bericht en berichten van andere facturen of tenants blijven ongemoeid.

Systeemgrens: alleen `aiosmtplib.send` is vervangen. Database (echte SQLite-sessie met `create_all`), auditdienst,
actor en repository lopen echt. Niet gemeten: rijsloten onder gelijktijdigheid (alleen PostgreSQL).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable
from src.core.repositories.receivable_repository import ReceivableChanges, ReceivableRepository
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

WACHTWOORD = "geheim-ww-Zx81"
MAX_POGINGEN = 3


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


async def _draai(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

    await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(sessie))


async def _factuur(sessie: AsyncSession, tenant_id: int, rij_id: int, status: str = "open") -> int:
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=tenant_id,
            customer_name="Bakkerij De Korst",
            customer_email="administratie@dekorst.example",
            invoice_number=f"F-2026-{rij_id:03d}",
            amount=Decimal("100.00"),
            currency="EUR",
            due_date=date(2026, 9, 1),
            status=status,
            source="handmatig",
        )
    )
    await sessie.commit()
    return rij_id


async def _bericht(
    sessie: AsyncSession,
    tenant_id: int,
    receivable_id: int | None,
    *,
    status: str = "klaar",
    pogingen: int = 0,
    kind: str = "herinnering",
) -> int:
    rij = OutgoingMessage(
        tenant_id=tenant_id,
        receivable_id=receivable_id,
        channel="email",
        kind=kind,
        recipient="administratie@dekorst.example",
        subject="Betalingsherinnering",
        body="Geachte heer, mevrouw, wij hebben nog geen betaling ontvangen.",
        status=status,
        pogingen=pogingen,
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


async def _herlees(sessie: AsyncSession, bericht_id: int) -> SimpleNamespace:
    sessie.expire_all()
    rij = await sessie.get(OutgoingMessage, bericht_id)
    assert rij is not None
    return SimpleNamespace(status=rij.status, pogingen=rij.pogingen, foutreden=rij.foutreden)


async def _auditregels(sessie: AsyncSession, tenant_id: int) -> list[object]:
    from src.core.governance.models import AuditLog

    vraag = select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id)
    return list((await sessie.execute(vraag)).scalars().all())


def _tekst(regel: object) -> str:
    velden = ("event_type", "action", "resource", "description", "event_metadata", "details")
    return json.dumps({v: getattr(regel, v, None) for v in velden}, default=str).lower()


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    db_session.add(Tenant(id=1, name="T1", slug="geen-brief-1"))
    db_session.add(Tenant(id=2, name="T2", slug="geen-brief-2"))
    await db_session.commit()
    zet_testmailbox(monkeypatch, wachtwoord=WACHTWOORD)
    return installeer_smtp_dubbel(monkeypatch)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeVerzendtaakLeestDeStatusOpnieuw:
    async def test_a_paid_receivable_gets_no_letter(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _bericht(db_session, 1, 10)

        await _draai(db_session)

        assert stand.ontvangen == []

    async def test_the_message_of_a_paid_receivable_is_cancelled(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        bid = await _bericht(db_session, 1, 10)

        await _draai(db_session)

        rij = await _herlees(db_session, bid)
        assert (rij.status, rij.pogingen) == ("mislukt", MAX_POGINGEN)
        assert (rij.foutreden or "").startswith("Geannuleerd:")

    async def test_a_cancelled_message_is_not_picked_up_again(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _bericht(db_session, 1, 10)
        await _draai(db_session)

        await _draai(db_session)

        assert (stand.ontvangen, len(await _auditregels(db_session, 1))) == ([], 1)

    async def test_the_cancellation_leaves_an_audit_line_in_the_own_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        bid = await _bericht(db_session, 1, 10)

        await _draai(db_session)

        regels = [_tekst(r) for r in await _auditregels(db_session, 1)]
        assert any(
            "debiteuren_bericht_geannuleerd" in r and f"outgoing_message:{bid}" in r for r in regels
        )

    async def test_the_audit_line_has_no_personal_data(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _bericht(db_session, 1, 10)

        await _draai(db_session)

        tekst = " ".join(_tekst(r) for r in await _auditregels(db_session, 1))
        assert "dekorst" not in tekst and "bakkerij" not in tekst

    async def test_the_other_tenant_gets_no_audit_line(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _bericht(db_session, 1, 10)

        await _draai(db_session)

        assert await _auditregels(db_session, 2) == []

    @pytest.mark.parametrize("status", ["open", "herinnerd", "geescaleerd"])
    async def test_an_outstanding_receivable_still_gets_its_letter(
        self, db_session: AsyncSession, stand: SmtpDubbel, status: str
    ) -> None:
        await _factuur(db_session, 1, 10, status)
        bid = await _bericht(db_session, 1, 10, kind="aanmaning")

        await _draai(db_session)

        assert ((await _herlees(db_session, bid)).status, len(stand.ontvangen)) == ("verzonden", 1)

    async def test_a_failed_message_with_attempts_left_is_also_cancelled_when_paid(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        bid = await _bericht(db_session, 1, 10, status="mislukt", pogingen=1)

        await _draai(db_session)

        rij = await _herlees(db_session, bid)
        assert (stand.ontvangen, rij.pogingen, (rij.foutreden or "")[:11]) == (
            [],
            MAX_POGINGEN,
            "Geannuleerd",
        )

    async def test_a_message_without_a_receivable_is_still_sent(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _bericht(db_session, 1, None)

        await _draai(db_session)

        assert (await _herlees(db_session, bid)).status == "verzonden"

    async def test_a_receivable_of_another_tenant_does_not_count_and_blocks_the_letter(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        # Een bericht van tenant 1 dat naar een factuur van tenant 2 wijst: de factuur bestaat niet binnen de tenant.
        await _factuur(db_session, 2, 20, "open")
        bid = await _bericht(db_session, 1, 20)

        await _draai(db_session)

        assert (stand.ontvangen, (await _herlees(db_session, bid)).status) == ([], "mislukt")

    async def test_a_cancelled_message_does_not_stop_the_others(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _factuur(db_session, 2, 20, "open")
        await _bericht(db_session, 1, 10)
        tweede = await _bericht(db_session, 2, 20)

        await _draai(db_session)

        assert ((await _herlees(db_session, tweede)).status, len(stand.ontvangen)) == (
            "verzonden",
            1,
        )

    async def test_the_receivable_stays_paid_after_the_run(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10, "betaald")
        await _bericht(db_session, 1, 10)

        await _draai(db_session)

        db_session.expire_all()
        rij = await db_session.get(Receivable, 10)
        assert rij is not None and rij.status == "betaald"


@pytest.mark.unit
@pytest.mark.asyncio
class TestBetaaldZettenAnnuleertHetBericht:
    async def _betaald(self, sessie: AsyncSession, tenant_id: int, rij_id: int) -> None:
        repo = ReceivableRepository(sessie)
        await repo.update(tenant_id, rij_id, ReceivableChanges(status="betaald"))
        await sessie.commit()

    async def test_a_ready_message_is_cancelled_when_the_receivable_is_marked_paid(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        bid = await _bericht(db_session, 1, 10)

        await self._betaald(db_session, 1, 10)

        rij = await _herlees(db_session, bid)
        assert (rij.status, rij.pogingen, (rij.foutreden or "")[:11]) == (
            "mislukt",
            MAX_POGINGEN,
            "Geannuleerd",
        )

    async def test_the_cancelled_message_is_never_sent_afterwards(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        await _bericht(db_session, 1, 10)
        await self._betaald(db_session, 1, 10)

        await _draai(db_session)

        assert stand.ontvangen == []

    async def test_a_failed_message_with_attempts_left_is_cancelled_too(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        bid = await _bericht(db_session, 1, 10, status="mislukt", pogingen=2)

        await self._betaald(db_session, 1, 10)

        assert (await _herlees(db_session, bid)).pogingen == MAX_POGINGEN

    async def test_a_message_that_was_already_sent_is_left_alone(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        bid = await _bericht(db_session, 1, 10, status="verzonden")

        await self._betaald(db_session, 1, 10)

        rij = await _herlees(db_session, bid)
        assert (rij.status, rij.foutreden) == ("verzonden", None)

    async def test_a_message_of_another_receivable_is_left_alone(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        await _factuur(db_session, 1, 11)
        ander = await _bericht(db_session, 1, 11)

        await self._betaald(db_session, 1, 10)

        assert (await _herlees(db_session, ander)).status == "klaar"

    async def test_a_message_of_another_tenant_is_left_alone(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        await _factuur(db_session, 2, 110)
        vreemd = await _bericht(db_session, 2, 110)

        await self._betaald(db_session, 1, 10)

        assert (await _herlees(db_session, vreemd)).status == "klaar"

    async def test_changing_another_field_does_not_cancel(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        bid = await _bericht(db_session, 1, 10)
        repo = ReceivableRepository(db_session)

        await repo.update(1, 10, ReceivableChanges(customer_name="Nieuwe Naam"))
        await db_session.commit()

        assert (await _herlees(db_session, bid)).status == "klaar"

    async def test_reopening_a_paid_receivable_does_not_revive_a_cancelled_message(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _factuur(db_session, 1, 10)
        bid = await _bericht(db_session, 1, 10)
        await self._betaald(db_session, 1, 10)
        repo = ReceivableRepository(db_session)

        await repo.update(1, 10, ReceivableChanges(status="open", reden="Terugboeking"))
        await db_session.commit()
        await _draai(db_session)

        assert (stand.ontvangen, (await _herlees(db_session, bid)).status) == ([], "mislukt")
