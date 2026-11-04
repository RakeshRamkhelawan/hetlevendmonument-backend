"""Een escalatie meldt zich bij de medewerkers -- debiteuren vanzelf afronden, B3 (2026-10-20).

Gemeten door de acceptant (2026-10-19): "escalatie meldt niets", alleen de status werd "Geescaleerd". Nu zet de
dagelijkse opvolging bij een escalatie een melding in de meldingenlijst van de app (`notifications`, dezelfde tabel
als de HR-melding) voor elke ACTIEVE gebruiker van DIE tenant met `receivables:propose`:

    "Factuur F-10 van Bakkerij De Korst is na 14 dagen niet betaald en is geescaleerd. Stel zo nodig een aanmaning voor."

De melding gaat naar medewerkers, NOOIT naar de debiteur: er komt geen `outgoing_messages`-rij en geen mail. Een
kapotte melding mag de escalatie niet terugdraaien (best_effort). Alleen de rechtencontrole (`RBACService
.user_has_permission`) en `aiosmtplib.send` zijn vervangen; de echte rolzaaier staat in
`tests/integration/test_debiteuren_vanzelf_afronden.py`.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.outgoing_message_models import OutgoingMessage
from src.core.models.rbac_models import Tenant, User
from src.core.models.receivable_models import Receivable
from src.domains.notifications.models import Notification
from tests.unit.debiteuren._smtp_dubbel import SmtpDubbel, installeer_smtp_dubbel, zet_testmailbox

NU = datetime(2099, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
DAG = timedelta(days=1)
KLANT_MAIL = "administratie@dekorst.example"


def _fabriek(sessie: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _sessie() -> AsyncIterator[AsyncSession]:
        yield sessie

    return _sessie


async def _draai(sessie: AsyncSession, mag: set[int]) -> None:
    """Een run van de opvolging; `mag` zijn de gebruikers-id's die `receivables:propose` hebben."""
    from src.core.services.rbac_service import RBACService
    from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

    async def _heeft(self: object, user_id: int, permission: str, tenant_id: int) -> bool:
        return permission == "receivables:propose" and user_id in mag

    with patch.object(RBACService, "user_has_permission", _heeft):
        await volg_debiteuren_op_async(sessie_fabriek=_fabriek(sessie), nu=NU)


async def _gebruiker(
    sessie: AsyncSession, tenant_id: int, email: str, *, actief: bool = True
) -> int:
    rij = User(
        email=email,
        hashed_password="x",
        tenant_id=tenant_id,
        is_active=actief,
        is_superuser=False,
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


async def _herinnerd(
    sessie: AsyncSession,
    tenant_id: int,
    rij_id: int,
    dagen_geleden: float,
    *,
    naam: str = "Bakkerij De Korst",
) -> int:
    moment = NU - timedelta(days=dagen_geleden)
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=tenant_id,
            customer_name=naam,
            customer_email=KLANT_MAIL,
            invoice_number=f"F-{rij_id}",
            amount=Decimal("100.00"),
            currency="EUR",
            due_date=date(2099, 1, 1),
            status="herinnerd",
            source="handmatig",
            herinnerd_op=moment,
            created_at=NU - 90 * DAG,
        )
    )
    await sessie.flush()
    sessie.add(
        OutgoingMessage(
            tenant_id=tenant_id,
            receivable_id=rij_id,
            channel="email",
            kind="herinnering",
            recipient="klant@klant.example",
            subject="Herinnering",
            body="Tekst",
            status="verzonden",
            verzonden_op=moment,
            hitl_ticket_ref=f"hitl-melding-{tenant_id}-{rij_id}",
        )
    )
    await sessie.commit()
    return rij_id


async def _meldingen(sessie: AsyncSession, user_id: int | None = None) -> list[Notification]:
    vraag = select(Notification).order_by(Notification.id)
    if user_id is not None:
        vraag = vraag.where(Notification.user_id == user_id)
    return list((await sessie.execute(vraag)).scalars().all())


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    db_session.add(Tenant(id=1, name="T1", slug="melding-1", settings={}))
    db_session.add(Tenant(id=2, name="T2", slug="melding-2", settings={}))
    await db_session.commit()
    zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-Zx81")
    return installeer_smtp_dubbel(monkeypatch)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeMelding:
    async def test_a_user_with_the_right_gets_a_notification(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        assert len(await _meldingen(db_session, anna)) == 1

    async def test_the_text_is_dutch_and_names_invoice_customer_and_days(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        melding = (await _meldingen(db_session, anna))[0]
        assert melding.body == (
            "Factuur F-10 van Bakkerij De Korst is na 14 dagen niet betaald en is geescaleerd. "
            "Stel zo nodig een aanmaning voor."
        )

    async def test_the_title_names_the_invoice(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        assert (await _meldingen(db_session, anna))[0].title == "Factuur F-10 is geescaleerd"

    async def test_the_notification_points_to_the_debtor_screen(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        data = (await _meldingen(db_session, anna))[0].data
        assert (data["link"], data["receivable_id"]) == ("/debiteuren", 10)

    async def test_the_type_and_channel_are_those_of_the_inbox(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        melding = (await _meldingen(db_session, anna))[0]
        assert (melding.type, melding.channel, melding.tenant_id) == (
            "debiteuren_escalatie",
            "in_app",
            1,
        )

    async def test_the_text_names_the_own_term_of_the_tenant(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        tenant = await db_session.get(Tenant, 1)
        assert tenant is not None
        tenant.settings = {"escalatie_na_dagen": 7}
        await db_session.commit()
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=8)

        await _draai(db_session, {anna})

        assert "is na 7 dagen niet betaald" in (await _meldingen(db_session, anna))[0].body

    async def test_every_user_with_the_right_gets_one(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        bram = await _gebruiker(db_session, 1, "bram@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna, bram})

        assert (
            len(await _meldingen(db_session, anna)),
            len(await _meldingen(db_session, bram)),
        ) == (1, 1)

    async def test_a_user_without_the_right_gets_nothing(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        zonder = await _gebruiker(db_session, 1, "zonder@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        assert await _meldingen(db_session, zonder) == []

    async def test_an_inactive_user_gets_nothing(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        weg = await _gebruiker(db_session, 1, "weg@melding.test", actief=False)
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {weg})

        assert await _meldingen(db_session, weg) == []

    async def test_a_user_of_another_tenant_gets_nothing(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        vreemd = await _gebruiker(db_session, 2, "vreemd@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {vreemd})

        assert await _meldingen(db_session, vreemd) == []

    async def test_a_dossier_that_does_not_escalate_gives_no_notification(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=13)

        await _draai(db_session, {anna})

        assert await _meldingen(db_session) == []

    async def test_a_second_run_does_not_notify_again(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)
        await _draai(db_session, {anna})

        await _draai(db_session, {anna})

        assert len(await _meldingen(db_session, anna)) == 1

    async def test_two_dossiers_give_two_notifications(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)
        await _herinnerd(db_session, 1, 11, dagen_geleden=20)

        await _draai(db_session, {anna})

        assert len(await _meldingen(db_session, anna)) == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestNietsNaarDeDebiteur:
    async def test_no_mail_leaves(self, db_session: AsyncSession, stand: SmtpDubbel) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        assert stand.ontvangen == []

    async def test_no_message_is_queued(self, db_session: AsyncSession, stand: SmtpDubbel) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        aantal = (await db_session.execute(select(func.count(OutgoingMessage.id)))).scalar_one()
        assert aantal == 1  # alleen de verzonden brief van voor de escalatie

    async def test_the_notification_has_no_email_address(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        anna = await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, {anna})

        melding = (await _meldingen(db_session, anna))[0]
        assert KLANT_MAIL not in f"{melding.title} {melding.body} {melding.data}"


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenKapotteMeldingBlokkeertDeEscalatieNiet:
    async def test_the_dossier_is_still_escalated_when_the_notification_fails(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        from src.core.services.rbac_service import RBACService
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

        await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        async def _kapot(self: object, *args: object) -> bool:
            raise RuntimeError("rechtenbron weg")

        with patch.object(RBACService, "user_has_permission", _kapot):
            await volg_debiteuren_op_async(sessie_fabriek=_fabriek(db_session), nu=NU)

        db_session.expire_all()
        rij = await db_session.get(Receivable, 10)
        assert rij is not None and rij.status == "geescaleerd"

    async def test_nobody_with_the_right_is_not_an_error(
        self, db_session: AsyncSession, stand: SmtpDubbel
    ) -> None:
        await _gebruiker(db_session, 1, "anna@melding.test")
        await _herinnerd(db_session, 1, 10, dagen_geleden=15)

        await _draai(db_session, set())

        db_session.expire_all()
        rij = await db_session.get(Receivable, 10)
        assert (rij.status if rij else None, await _meldingen(db_session)) == ("geescaleerd", [])
