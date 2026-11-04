"""De tenantcontext staat goed op het moment dat de auditregel en de wijziging geschreven worden.

Dag-2-bevinding (`debiteuren_tasks.py`): "de tenantcontext rond de auditregel is niet door een test
gedekt; de regel krijgt `tenant_id` expliciet mee, en op SQLite geeft dat geen zichtbaar
verschil". Dit bestand dekt dat voor BEIDE actors van Keten B: `verstuur_klare_berichten` (dag 2)
en `volg_debiteuren_op` (dag 3).

**Hoe gemeten.** Een SQLAlchemy `before_insert`/`before_update`-luisteraar op `AuditLog` en
`Receivable` noteert, per geschreven rij, de `tenant_id` van de rij en de tenantcontext (de
ContextVar) op dat moment. Dat is onafhankelijk van WELKE auditmethode de actor aanroept
(`log_action` of `log_event`) en zegt iets wat een expliciet meegegeven `tenant_id` niet kan
verhullen: een rij die wordt geschreven terwijl de context op een ander bedrijf staat (of leeg
is) valt direct op. Er is niets vervangen of ingekort; de luisteraar kijkt alleen.

**Mutatie** (op de echte bron, in een wegwerp-kopie van de test, niet in `src/`): `adopt_tenant`
in de actor vervangen door een lege context -> beide tests rood (zie de terugmelding).

**Wat dit NIET meet.** Dat PostgreSQL-RLS de rij ook echt filtert (alleen PostgreSQL, OP-151).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.governance.models import AuditLog
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

NU = datetime(2099, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
DAG = timedelta(days=1)

#: (soort, tenant_id van de rij, tenantcontext op het moment van schrijven)
Waarneming = tuple[str, int | None, int | None]


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


@pytest.fixture
def waarnemingen() -> Iterator[list[Waarneming]]:
    gezien: list[Waarneming] = []

    def _audit(mapper: object, connection: object, target: AuditLog) -> None:
        gezien.append(("audit", target.tenant_id, get_current_tenant_id()))

    def _factuur(mapper: object, connection: object, target: Receivable) -> None:
        gezien.append(("factuur", target.tenant_id, get_current_tenant_id()))

    def _bericht(mapper: object, connection: object, target: OutgoingMessage) -> None:
        gezien.append(("bericht", target.tenant_id, get_current_tenant_id()))

    event.listen(AuditLog, "before_insert", _audit)
    event.listen(Receivable, "before_update", _factuur)
    event.listen(OutgoingMessage, "before_update", _bericht)
    try:
        yield gezien
    finally:
        event.remove(AuditLog, "before_insert", _audit)
        event.remove(Receivable, "before_update", _factuur)
        event.remove(OutgoingMessage, "before_update", _bericht)


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    db_session.add(Tenant(id=1, name="T1", slug="deb-ctx-1"))
    db_session.add(Tenant(id=2, name="T2", slug="deb-ctx-2"))
    await db_session.commit()
    zet_testmailbox(monkeypatch)
    return installeer_smtp_dubbel(monkeypatch)


def _verzonden_brief(tenant_id: int, rij_id: int, moment: datetime | None) -> OutgoingMessage:
    """De brief die een `herinnerd` dossier hoort te hebben: zonder verzonden brief escaleert de
    opvolging niet (wfb-dag1 stap 2, test_herinnerd_is_een_feit.py)."""
    return OutgoingMessage(
        tenant_id=tenant_id,
        receivable_id=rij_id,
        channel="email",
        kind="herinnering",
        recipient="klant@klant.example",
        subject="Herinnering",
        body="Tekst",
        status="verzonden",
        verzonden_op=moment,
        hitl_ticket_ref=f"hitl-verzonden-{tenant_id}-{rij_id}",
    )


async def _factuur(sessie: AsyncSession, tenant_id: int, rij_id: int) -> None:
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=tenant_id,
            customer_name="Klant",
            customer_email="klant@klant.example",
            invoice_number=f"F-{rij_id}",
            amount=Decimal("10.00"),
            currency="EUR",
            due_date=date(2099, 1, 1),
            status="herinnerd",
            source="handmatig",
            herinnerd_op=NU - 15 * DAG,
            created_at=NU - 60 * DAG,
        )
    )
    await sessie.flush()
    # Zonder verzonden brief escaleert de opvolging niet (wfb-dag1 stap 2).
    sessie.add(_verzonden_brief(tenant_id, rij_id, NU - 15 * DAG))
    await sessie.commit()


async def _bericht(sessie: AsyncSession, tenant_id: int, ontvanger: str) -> None:
    sessie.add(
        OutgoingMessage(
            tenant_id=tenant_id,
            channel="email",
            kind="herinnering",
            recipient=ontvanger,
            subject="Herinnering",
            body="Tekst",
            status="klaar",
        )
    )
    await sessie.commit()


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantContextBijHetSchrijven:
    async def test_opvolgen_schrijft_elke_rij_in_de_context_van_zijn_eigen_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel, waarnemingen: list[Waarneming]
    ) -> None:
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

        await _factuur(db_session, 1, 1001)
        await _factuur(db_session, 2, 2002)

        await volg_debiteuren_op_async(sessie_fabriek=_fabriek(db_session), nu=NU)

        soorten = {soort for soort, _, _ in waarnemingen}
        fout = [w for w in waarnemingen if w[1] != w[2]]
        assert soorten >= {"audit", "factuur"}, (
            f"verwacht audit- en factuurschrijf, kreeg {waarnemingen}"
        )
        assert fout == [], f"(soort, tenant van de rij, context): {fout}"

    async def test_verzenden_schrijft_elke_rij_in_de_context_van_zijn_eigen_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel, waarnemingen: list[Waarneming]
    ) -> None:
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

        await _bericht(db_session, 1, "a@klant.example")
        await _bericht(db_session, 2, "b@klant.example")

        await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(db_session))

        soorten = {soort for soort, _, _ in waarnemingen}
        fout = [w for w in waarnemingen if w[1] != w[2]]
        assert soorten >= {"audit", "bericht"}, (
            f"verwacht audit- en berichtschrijf, kreeg {waarnemingen}"
        )
        assert fout == [], f"(soort, tenant van de rij, context): {fout}"

    async def test_de_waarnemer_ziet_een_verkeerde_context_ook_echt(
        self, db_session: AsyncSession, waarnemingen: list[Waarneming]
    ) -> None:
        """Vangnet voor de meting zelf: schrijf een rij van tenant 2 met een lege context."""
        db_session.add(Tenant(id=2, name="T2", slug="deb-ctx-vangnet"))
        await db_session.commit()
        await _factuur(db_session, 2, 2002)
        rij = await db_session.get(Receivable, 2002)
        assert rij is not None

        rij.status = "betaald"
        await db_session.commit()

        assert ("factuur", 2, None) in waarnemingen
