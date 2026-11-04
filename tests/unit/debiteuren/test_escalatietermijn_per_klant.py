"""Een eigen escalatietermijn per klant -- debiteuren vanzelf afronden (2026-10-20).

Besluit Rakesh 2026-10-20: "laat klant zijn eigen escalatietermijn kiezen". De termijn staat als `escalatie_na_dagen`
in `tenants.settings` (JSON, geen kolom, geen migratie, zoals de vier-ogen-keuze), is een geheel getal van 1 tot en
met 120 en is standaard 14. Wat hier gemeten wordt:

1. De leesregel: een ontbrekende, kapotte of onmogelijke waarde (0, 121, tekst, een float, een bool) valt terug op 14.
2. De schrijfregel: 1 en 120 mogen, 0, 121, een negatief getal, een bool, een tekst en een float worden geweigerd;
   de rest van `settings` blijft staan; een onbekende tenant geeft een fout.
3. De dagelijkse opvolging gebruikt per tenant de EIGEN termijn: een tenant met 7 escaleert na 7 dagen, een tenant
   met 21 niet (maar wel na 21), een tenant zonder instelling na 14. De grens is per tenant inclusief.

Systeemgrens: echte SQLite-sessie met `create_all`; de klok is een parameter van `volg_debiteuren_op_async`.
Niet gemeten: de beheerdersroute en het scherm (eigen tests), en rijsloten (alleen PostgreSQL).

Mutatiebewijs: zie de commitboodschap.
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


async def _draai(sessie: AsyncSession) -> None:
    from src.core.tasks.debiteuren_tasks import volg_debiteuren_op_async

    await volg_debiteuren_op_async(sessie_fabriek=_fabriek(sessie), nu=NU)


async def _herinnerd(
    sessie: AsyncSession, tenant_id: int, rij_id: int, dagen_geleden: float
) -> int:
    moment = NU - timedelta(days=dagen_geleden)
    sessie.add(
        Receivable(
            id=rij_id,
            tenant_id=tenant_id,
            customer_name="Bakkerij De Korst",
            customer_email="administratie@dekorst.example",
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
            hitl_ticket_ref=f"hitl-termijn-{tenant_id}-{rij_id}",
        )
    )
    await sessie.commit()
    return rij_id


async def _status(sessie: AsyncSession, rij_id: int) -> str:
    sessie.expire_all()
    rij = await sessie.get(Receivable, rij_id)
    assert rij is not None
    return rij.status


async def _tenant(sessie: AsyncSession, tenant_id: int, settings: object) -> None:
    sessie.add(
        Tenant(id=tenant_id, name=f"T{tenant_id}", slug=f"termijn-{tenant_id}", settings=settings)
    )
    await sessie.commit()


@pytest_asyncio.fixture
async def tenants(db_session: AsyncSession) -> AsyncSession:
    await _tenant(db_session, 1, {"escalatie_na_dagen": 7})
    await _tenant(db_session, 2, {"escalatie_na_dagen": 21})
    await _tenant(db_session, 3, {})
    return db_session


class TestDeLeesregel:
    @pytest.mark.parametrize(
        ("settings", "verwacht"),
        [
            (None, 14),
            ({}, 14),
            ("kapot", 14),
            ([], 14),
            ({"escalatie_na_dagen": 7}, 7),
            ({"escalatie_na_dagen": 1}, 1),
            ({"escalatie_na_dagen": 120}, 120),
            ({"escalatie_na_dagen": 0}, 14),
            ({"escalatie_na_dagen": 121}, 14),
            ({"escalatie_na_dagen": -3}, 14),
            ({"escalatie_na_dagen": "7"}, 14),
            ({"escalatie_na_dagen": 7.5}, 14),
            ({"escalatie_na_dagen": True}, 14),
            ({"escalatie_na_dagen": None}, 14),
            ({"four_eyes_actions": ["send_payment_reminder"]}, 14),
        ],
    )
    def test_the_term_of_a_tenant(self, settings: object, verwacht: int) -> None:
        from src.core.governance.debiteuren_instellingen import escalatie_na_dagen_uit_settings

        assert escalatie_na_dagen_uit_settings(settings) == verwacht

    def test_the_default_is_fourteen_days(self) -> None:
        from src.core.governance.debiteuren_instellingen import STANDAARD_ESCALATIE_NA_DAGEN

        assert STANDAARD_ESCALATIE_NA_DAGEN == 14

    def test_the_task_constant_equals_the_default(self) -> None:
        # De taak heeft een eigen getal (geen governance-import op moduleniveau, DSM-plafond); dit houdt ze gelijk.
        from src.core.governance.debiteuren_instellingen import STANDAARD_ESCALATIE_NA_DAGEN
        from src.core.tasks.debiteuren_tasks import ESCALATIE_NA_DAGEN

        assert ESCALATIE_NA_DAGEN == STANDAARD_ESCALATIE_NA_DAGEN


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeSchrijfregel:
    async def test_a_valid_term_is_stored_and_old_and_new_come_back(
        self, db_session: AsyncSession
    ) -> None:
        from src.core.governance.debiteuren_instellingen import (
            lees_escalatie_na_dagen,
            schrijf_escalatie_na_dagen,
        )

        await _tenant(db_session, 1, {})

        oud_nieuw = await schrijf_escalatie_na_dagen(db_session, tenant_id=1, dagen=30)

        assert (oud_nieuw, await lees_escalatie_na_dagen(db_session, tenant_id=1)) == ((14, 30), 30)

    @pytest.mark.parametrize("dagen", [1, 120])
    async def test_the_limits_are_allowed(self, db_session: AsyncSession, dagen: int) -> None:
        from src.core.governance.debiteuren_instellingen import schrijf_escalatie_na_dagen

        await _tenant(db_session, 1, {})

        assert (await schrijf_escalatie_na_dagen(db_session, tenant_id=1, dagen=dagen))[1] == dagen

    @pytest.mark.parametrize("dagen", [0, 121, -1, 500, True, "7", 7.5, None])
    async def test_an_impossible_term_is_refused_and_nothing_changes(
        self, db_session: AsyncSession, dagen: object
    ) -> None:
        from src.core.governance.debiteuren_instellingen import (
            lees_escalatie_na_dagen,
            schrijf_escalatie_na_dagen,
        )

        await _tenant(db_session, 1, {"escalatie_na_dagen": 9})

        with pytest.raises(ValueError):
            await schrijf_escalatie_na_dagen(db_session, tenant_id=1, dagen=dagen)  # type: ignore[arg-type]

        assert await lees_escalatie_na_dagen(db_session, tenant_id=1) == 9

    async def test_the_rest_of_the_settings_stays(self, db_session: AsyncSession) -> None:
        from src.core.governance.debiteuren_instellingen import schrijf_escalatie_na_dagen

        await _tenant(db_session, 1, {"four_eyes_actions": ["send_payment_reminder"], "x": 1})

        await schrijf_escalatie_na_dagen(db_session, tenant_id=1, dagen=5)

        db_session.expire_all()
        tenant = await db_session.get(Tenant, 1)
        assert tenant is not None and tenant.settings == {
            "four_eyes_actions": ["send_payment_reminder"],
            "x": 1,
            "escalatie_na_dagen": 5,
        }

    async def test_an_unknown_tenant_is_an_error(self, db_session: AsyncSession) -> None:
        from src.core.governance.debiteuren_instellingen import schrijf_escalatie_na_dagen

        with pytest.raises(LookupError):
            await schrijf_escalatie_na_dagen(db_session, tenant_id=999, dagen=7)

    async def test_a_term_of_another_tenant_is_not_touched(self, db_session: AsyncSession) -> None:
        from src.core.governance.debiteuren_instellingen import (
            lees_escalatie_na_dagen,
            schrijf_escalatie_na_dagen,
        )

        await _tenant(db_session, 1, {})
        await _tenant(db_session, 2, {"escalatie_na_dagen": 21})

        await schrijf_escalatie_na_dagen(db_session, tenant_id=1, dagen=3)

        assert await lees_escalatie_na_dagen(db_session, tenant_id=2) == 21


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeOpvolgingGebruiktDeEigenTermijn:
    async def test_a_tenant_with_seven_days_escalates_after_seven_days(
        self, tenants: AsyncSession
    ) -> None:
        await _herinnerd(tenants, 1, 10, dagen_geleden=8)

        await _draai(tenants)

        assert await _status(tenants, 10) == "geescaleerd"

    async def test_the_limit_is_inclusive_per_tenant(self, tenants: AsyncSession) -> None:
        await _herinnerd(tenants, 1, 10, dagen_geleden=7)

        await _draai(tenants)

        assert await _status(tenants, 10) == "geescaleerd"

    async def test_just_under_the_own_term_does_not_escalate(self, tenants: AsyncSession) -> None:
        await _herinnerd(tenants, 1, 10, dagen_geleden=6.99)

        await _draai(tenants)

        assert await _status(tenants, 10) == "herinnerd"

    async def test_a_tenant_with_twentyone_days_does_not_escalate_after_eight(
        self, tenants: AsyncSession
    ) -> None:
        await _herinnerd(tenants, 2, 20, dagen_geleden=8)

        await _draai(tenants)

        assert await _status(tenants, 20) == "herinnerd"

    async def test_a_tenant_with_twentyone_days_does_not_escalate_at_twenty(
        self, tenants: AsyncSession
    ) -> None:
        await _herinnerd(tenants, 2, 20, dagen_geleden=20)

        await _draai(tenants)

        assert await _status(tenants, 20) == "herinnerd"

    async def test_a_tenant_with_twentyone_days_escalates_at_twentyone(
        self, tenants: AsyncSession
    ) -> None:
        await _herinnerd(tenants, 2, 20, dagen_geleden=21)

        await _draai(tenants)

        assert await _status(tenants, 20) == "geescaleerd"

    async def test_a_tenant_without_a_setting_keeps_fourteen_days(
        self, tenants: AsyncSession
    ) -> None:
        await _herinnerd(tenants, 3, 30, dagen_geleden=13)
        await _herinnerd(tenants, 3, 31, dagen_geleden=14)

        await _draai(tenants)

        assert (await _status(tenants, 30), await _status(tenants, 31)) == (
            "herinnerd",
            "geescaleerd",
        )

    async def test_every_tenant_is_judged_by_its_own_term_in_one_run(
        self, tenants: AsyncSession
    ) -> None:
        # Dezelfde 10 dagen oud: tenant 1 (7) escaleert, tenant 2 (21) en tenant 3 (14) niet.
        await _herinnerd(tenants, 1, 10, dagen_geleden=10)
        await _herinnerd(tenants, 2, 20, dagen_geleden=10)
        await _herinnerd(tenants, 3, 30, dagen_geleden=10)

        await _draai(tenants)

        assert [await _status(tenants, i) for i in (10, 20, 30)] == [
            "geescaleerd",
            "herinnerd",
            "herinnerd",
        ]

    async def test_an_impossible_stored_term_falls_back_to_fourteen(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 4, {"escalatie_na_dagen": 0})
        await _herinnerd(db_session, 4, 40, dagen_geleden=10)
        await _herinnerd(db_session, 4, 41, dagen_geleden=15)

        await _draai(db_session)

        assert (await _status(db_session, 40), await _status(db_session, 41)) == (
            "herinnerd",
            "geescaleerd",
        )


@pytest.mark.asyncio
class TestWeigeringInHetNederlands:
    """Acceptatie 2026-10-21: de 403 bij het wijzigen van de termijn was Engels ("Admin access required")."""

    @staticmethod
    def _gebruiker(rollen: list[str]) -> object:
        from src.core.auth.auth_service import UserResponse

        return UserResponse(id=5, email="medewerker@bedrijf.example", tenant_id=1, roles=rollen)

    async def test_a_non_administrator_gets_a_dutch_403(self) -> None:
        from fastapi import HTTPException

        from src.core.api.v1.receivables.dependencies import vereis_beheerder

        with pytest.raises(HTTPException) as fout:
            await vereis_beheerder(current_user=self._gebruiker(["debiteuren"]), db=None)  # type: ignore[arg-type]

        assert (fout.value.status_code, fout.value.detail) == (
            403,
            "Alleen een beheerder mag de escalatietermijn wijzigen.",
        )

    async def test_an_administrator_passes(self) -> None:
        from src.core.api.v1.receivables.dependencies import vereis_beheerder

        gebruiker = self._gebruiker(["admin"])

        assert await vereis_beheerder(current_user=gebruiker, db=None) is gebruiker  # type: ignore[arg-type]
