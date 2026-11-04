"""Een kapotte auditschrijving blokkeert de verzending niet (best_effort) -- Keten B dag 2.

`test_verzenden.py` laat de auditdienst echt lopen; dit bestand zet precies EEN ding anders: de
aanroep `AuditService.log_action` werpt. De brief is dan al de deur uit en de statuswijziging is
gecommit, en dat moet zo blijven. De patch staat alleen in deze module, zodat `test_verzenden.py`
de echte auditdienst blijft meten.

Mutatie die dit moet betrappen: de aanroep in `_log_uitkomst` uit `best_effort` halen. Dan werpt
de run en blijft de volgende rij onverwerkt.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.governance.audit import AuditService
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox


@asynccontextmanager
async def _sessie_van(sessie: AsyncSession) -> AsyncIterator[AsyncSession]:
    yield sessie


async def _bericht(sessie: AsyncSession, ontvanger: str) -> int:
    rij = OutgoingMessage(
        tenant_id=1,
        channel="email",
        kind="herinnering",
        recipient=ontvanger,
        subject="Herinnering",
        body="Tekst",
        status="klaar",
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    db_session.add(Tenant(id=1, name="T1", slug="deb-audit-faalt"))
    await db_session.commit()
    zet_testmailbox(monkeypatch)

    async def _kapot(*args: object, **kwargs: object) -> None:
        raise RuntimeError("auditdienst kapot")

    monkeypatch.setattr(AuditService, "log_action", _kapot)
    return installeer_smtp_dubbel(monkeypatch)


async def _draai(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten_async

    await verstuur_klare_berichten_async(sessie_fabriek=lambda: _sessie_van(sessie))


@pytest.mark.unit
@pytest.mark.asyncio
class TestKapotteAuditBlokkeertVerzendingNiet:
    async def test_de_run_werpt_niet_als_de_auditschrijving_faalt(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _bericht(db_session, "a@klant.example")

        await _draai(db_session)

        assert len(stand.ontvangen) == 1

    async def test_het_bericht_blijft_verzonden_als_de_auditschrijving_faalt(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        bid = await _bericht(db_session, "a@klant.example")

        await _draai(db_session)

        db_session.expire_all()
        rij = await db_session.get(OutgoingMessage, bid)
        assert rij is not None and (rij.status, rij.verzonden_op is not None) == ("verzonden", True)

    async def test_een_tweede_bericht_wordt_nog_verstuurd_na_een_kapotte_audit(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _bericht(db_session, "a@klant.example")
        await _bericht(db_session, "b@klant.example")

        await _draai(db_session)

        assert sorted(b.ontvanger for b in stand.ontvangen) == [
            "a@klant.example",
            "b@klant.example",
        ]
