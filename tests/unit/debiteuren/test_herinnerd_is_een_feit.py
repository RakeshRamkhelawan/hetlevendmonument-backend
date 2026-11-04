"""`herinnerd` is een feit, geen keuze (wfb-dag1 stap 2).

Een vordering staat pas op `herinnerd` als er aantoonbaar een brief is verstuurd: de verzendlus
(`verstuur_klare_berichten`) zet de status op het moment dat het bericht `verzonden` is, met
`herinnerd_op` gelijk aan `verzonden_op`. Niemand anders kan hem zetten: de PATCH-route niet
(422), de repository niet (ValueError), en het klaarzetten van een brief ook niet (dat legt
alleen een bericht `klaar` neer).

De escalatie leunt op die datum. Daarom escaleert `volg_debiteuren_op` alleen een dossier
waarvoor een VERZONDEN bericht bestaat -- de vangrail voor rijen die nog met de hand of door
een workflow op `herinnerd` zijn gezet (docs/workflowbuilder-debiteuren.md, risico 4).

Systeemgrens: alleen `aiosmtplib.send` is vervangen (`_smtp_dubbel.py`). Database (SQLite met
`create_all`), repository, verzendlus en opvolging lopen echt.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable
from src.core.repositories.receivable_repository import ReceivableChanges, ReceivableRepository
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox
from tests.unit.debiteuren.test_api_verloop import _zet_factuur as _zet_factuur_api
from tests.unit.debiteuren.test_api_verloop import api  # noqa: F401 - fixture

NU = datetime(2099, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
DAG = timedelta(days=1)
URL = "/api/v1/receivables"


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


def _utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def smtp(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    db_session.add(Tenant(id=1, name="T1", slug="deb-feit-1"))
    await db_session.commit()
    zet_testmailbox(monkeypatch)
    return installeer_smtp_dubbel(monkeypatch)


async def _factuur(
    sessie: AsyncSession,
    *,
    rij_id: int = 4001,
    status: str = "open",
    herinnerd_op: datetime | None = None,
) -> int:
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=1,
            customer_name="Bakkerij De Korst",
            customer_email="administratie@dekorst.example",
            invoice_number=f"F-{rij_id}",
            amount=Decimal("100.00"),
            currency="EUR",
            due_date=date(2099, 1, 1),
            status=status,
            source="handmatig",
            herinnerd_op=herinnerd_op,
            created_at=NU - 60 * DAG,
        )
    )
    await sessie.commit()
    return rij_id


async def _bericht(
    sessie: AsyncSession,
    receivable_id: int,
    *,
    status: str = "klaar",
    verzonden_op: datetime | None = None,
) -> int:
    rij = OutgoingMessage(
        tenant_id=1,
        receivable_id=receivable_id,
        channel="email",
        kind="herinnering",
        recipient="administratie@dekorst.example",
        subject="Herinnering factuur",
        body="Uw factuur staat nog open.",
        status=status,
        verzonden_op=verzonden_op,
        hitl_ticket_ref=f"hitl-feit-{receivable_id}-{status}",
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


async def _verstuur(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

    await verstuur_klare_berichten_async(sessie_fabriek=_fabriek(sessie))


async def _volg_op(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

    await volg_debiteuren_op_async(sessie_fabriek=_fabriek(sessie), nu=NU)


async def _receivable(sessie: AsyncSession, rij_id: int) -> Receivable:
    sessie.expire_all()
    rij = await sessie.get(Receivable, rij_id)
    assert rij is not None
    return rij


@pytest.mark.unit
@pytest.mark.asyncio
class TestNiemandZetHerinnerdMetDeHand:
    async def test_een_patch_naar_herinnerd_geeft_422(
        self,
        api: AsyncClient,  # noqa: F811
        db_session: AsyncSession,
    ) -> None:
        rid = await _zet_factuur_api(db_session, "open")

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "herinnerd"})

        assert antwoord.status_code == 422, antwoord.text

    async def test_de_repository_weigert_herinnerd(self, db_session: AsyncSession) -> None:
        db_session.add(Tenant(id=1, name="T1", slug="deb-feit-repo"))
        await db_session.commit()
        rid = await _factuur(db_session)

        with pytest.raises(ValueError, match="herinnerd"):
            await ReceivableRepository(db_session).update(
                1, rid, ReceivableChanges(status="herinnerd")
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeVerzendlusZetHerinnerd:
    async def test_een_verzonden_brief_zet_de_vordering_op_herinnerd(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session)
        await _bericht(db_session, rid)

        await _verstuur(db_session)

        assert (await _receivable(db_session, rid)).status == "herinnerd"

    async def test_herinnerd_op_is_het_moment_van_verzenden(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session)
        bid = await _bericht(db_session, rid)

        await _verstuur(db_session)

        herinnerd_op = (await _receivable(db_session, rid)).herinnerd_op
        bericht = await db_session.get(OutgoingMessage, bid)
        assert bericht is not None
        assert herinnerd_op is not None and _utc(herinnerd_op) == _utc(bericht.verzonden_op)

    async def test_een_mislukte_verzending_laat_de_vordering_open(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        smtp.weiger_alles = True
        rid = await _factuur(db_session)
        await _bericht(db_session, rid)

        await _verstuur(db_session)

        rij = await _receivable(db_session, rid)
        assert (rij.status, rij.herinnerd_op) == ("open", None)

    async def test_een_inmiddels_betaalde_vordering_blijft_betaald(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session, status="betaald")
        await _bericht(db_session, rid)

        await _verstuur(db_session)

        assert (await _receivable(db_session, rid)).status == "betaald"


@pytest.mark.unit
@pytest.mark.asyncio
class TestEscalerenAlleenNaEenVerzondenBrief:
    async def test_herinnerd_zonder_verzonden_bericht_escaleert_niet(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session, status="herinnerd", herinnerd_op=NU - 30 * DAG)

        await _volg_op(db_session)

        assert (await _receivable(db_session, rid)).status == "herinnerd"

    async def test_herinnerd_met_alleen_een_klaar_bericht_escaleert_niet(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session, status="herinnerd", herinnerd_op=NU - 30 * DAG)
        await _bericht(db_session, rid, status="klaar")

        await _volg_op(db_session)

        assert (await _receivable(db_session, rid)).status == "herinnerd"

    async def test_herinnerd_met_een_verzonden_bericht_escaleert_wel(
        self, db_session: AsyncSession, smtp: SmtpDubbel
    ) -> None:
        rid = await _factuur(db_session, status="herinnerd", herinnerd_op=NU - 30 * DAG)
        await _bericht(db_session, rid, status="verzonden", verzonden_op=NU - 30 * DAG)

        await _volg_op(db_session)

        assert (await _receivable(db_session, rid)).status == "geescaleerd"
