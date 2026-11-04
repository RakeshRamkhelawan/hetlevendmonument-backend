"""Een kapotte auditschrijving blokkeert de escalatie niet (best_effort) -- Keten B dag 3.

`test_opvolgen.py` laat de auditdienst echt lopen; dit bestand zet precies EEN ding anders: elke
aanroep van de auditdienst werpt. Gemeten wordt dat de statuswijziging dan toch blijft staan
(backend-patterns par. 3: eerst de primaire data committen, daarna het logboek in `best_effort`)
en dat de run doorgaat naar het volgende dossier. De patch staat alleen in deze module, zodat
`test_opvolgen.py` de echte auditdienst blijft meten.

De patch zit op BEIDE auditingangen die dit project kent (`governance.audit.AuditService.log_action`
en `governance.services.audit_service.AuditService.log_event`): welke de bouwer kiest is zijn
zaak, de eis geldt voor allebei.

Mutatie die dit moet betrappen: de auditaanroep uit `best_effort` halen. Dan werpt de run en
blijft het volgende dossier onverwerkt (rood op `test_een_kapot_logboek_stopt_de_run_niet`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.governance.audit import AuditService as GovernanceAuditService
from src.core.governance.services.audit_service import AuditService as ServiceAuditService
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable

NU = datetime(2099, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
DAG = timedelta(days=1)


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


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


async def _zet(sessie: AsyncSession, tenant_id: int, rij_id: int) -> int:
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
    return rij_id


async def _status(sessie: AsyncSession, rij_id: int) -> str:
    sessie.expire_all()
    rij = await sessie.get(Receivable, rij_id)
    assert rij is not None
    return rij.status


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    db_session.add(Tenant(id=1, name="T1", slug="deb-opv-audit-1"))
    db_session.add(Tenant(id=2, name="T2", slug="deb-opv-audit-2"))
    await db_session.commit()

    async def _kapot(*args: object, **kwargs: object) -> None:
        raise RuntimeError("auditdienst kapot")

    monkeypatch.setattr(GovernanceAuditService, "log_action", _kapot)
    monkeypatch.setattr(ServiceAuditService, "log_event", _kapot)


async def _draai(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

    await volg_debiteuren_op_async(sessie_fabriek=_fabriek(sessie), nu=NU)


@pytest.mark.unit
@pytest.mark.asyncio
class TestKapotLogboekBlokkeertEscalatieNiet:
    async def test_de_escalatie_blijft_staan_als_de_auditschrijving_faalt(
        self, db_session: AsyncSession, stand: None
    ) -> None:
        rid = await _zet(db_session, 1, 1001)

        await _draai(db_session)

        assert await _status(db_session, rid) == "geescaleerd"

    async def test_een_kapot_logboek_stopt_de_run_niet(
        self, db_session: AsyncSession, stand: None
    ) -> None:
        """Het tweede dossier (andere tenant) wordt nog gewoon opgevolgd."""
        await _zet(db_session, 1, 1001)
        tweede = await _zet(db_session, 2, 2002)

        await _draai(db_session)

        assert await _status(db_session, tweede) == "geescaleerd"
