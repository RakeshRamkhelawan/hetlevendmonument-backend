"""Statusvolgorde van een debiteur -- Keten B dag 1 (brief 2026-10-06, besluit 5).

Gewenste volgorde: `open -> herinnerd -> geescaleerd`; vanuit ELKE status mag `betaald`; terug
van `betaald` alleen met een expliciete `reden`. Een ongeldige overgang geeft een ValueError
(zelfde soort fout als `_controleer_status`, "weiger luid") en laat de rij ongemoeid.

Techniek: toestandsovergangen. De overgangen staan hieronder expliciet, zodat een bouwer die
"alles toestaan" of "alles weigeren" implementeert in een van beide richtingen struikelt.

**Contract dat deze tests vastleggen:** `ReceivableChanges(status=..., reden="...")`; `reden`
is `str | None`. Een lege of blanke reden telt niet als reden.

**Wat de opstelling uitzet, nagelopen.** `tests/conftest.py::_reset_global_state` haalt de
globale tenantfilter weg: gewenst, het EIGEN filter van de repository wordt gemeten. Verder
actief: `enforce_testing_env` (TESTING=1, raakt niets hiervan). Geen patch op repository of
model; geen conftest in `tests/unit/debiteuren/`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.rbac_models import Tenant
from src.core.repositories.receivable_repository import (
    NewReceivable,
    ReceivableChanges,
    ReceivableRepository,
)

GELDIGE_OVERGANGEN = [
    ("open", "betaald"),
    ("herinnerd", "betaald"),
    ("geescaleerd", "betaald"),
]

ONGELDIGE_OVERGANGEN = [
    ("open", "geescaleerd"),  # overslaan van herinnerd
    ("herinnerd", "open"),  # terug zonder dat er betaald is
    ("geescaleerd", "herinnerd"),
    ("geescaleerd", "open"),
]

TERUG_VAN_BETAALD = ["open", "herinnerd", "geescaleerd"]

#: Wel een overgang in de toestandsmachine, maar NIET via `update` (wfb-dag1 stap 2):
#: `herinnerd` zet de verzendlus na een verzonden brief, `geescaleerd` de opvolging. Ook terug
#: van `betaald` (met reden) kan alleen naar `open`; de klok herstart dan met een nieuwe brief.
ALLEEN_DOOR_DE_KETEN = [
    ("open", "herinnerd"),
    ("herinnerd", "geescaleerd"),
    ("betaald", "herinnerd"),
    ("betaald", "geescaleerd"),
]


async def _tenant(session: AsyncSession, tenant_id: int) -> None:
    if await session.get(Tenant, tenant_id) is None:
        session.add(Tenant(id=tenant_id, name=f"T{tenant_id}", slug=f"deb-st-{tenant_id}"))
        await session.flush()


async def _rij_met_status(session: AsyncSession, tenant_id: int, status: str, nummer: str = "F-1"):  # type: ignore[no-untyped-def]
    """Zet een rij DIRECT op een status, zonder de overgangsregel te passeren."""
    from src.core.models.receivable_models import Receivable

    await _tenant(session, tenant_id)
    rij = Receivable(
        tenant_id=tenant_id,
        customer_name="Bakkerij De Korst",
        customer_email="administratie@dekorst.example",
        invoice_number=nummer,
        amount=Decimal("100.00"),
        currency="EUR",
        due_date=date(2026, 9, 1),
        status=status,
        source="handmatig",
    )
    session.add(rij)
    await session.flush()
    return rij


def _utc(waarde: datetime | None) -> datetime | None:
    """SQLite geeft naieve tijden terug; PostgreSQL bewaart de zone. Vergelijk in UTC."""
    if waarde is not None and waarde.tzinfo is None:
        return waarde.replace(tzinfo=timezone.utc)
    return waarde


@pytest.mark.unit
@pytest.mark.asyncio
class TestGeldigeOvergangen:
    @pytest.mark.parametrize(("van", "naar"), GELDIGE_OVERGANGEN)
    async def test_toegestane_statusovergang_slaagt(
        self, db_session: AsyncSession, van: str, naar: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, van)

        nieuw = await ReceivableRepository(db_session).update(
            1, rij.id, ReceivableChanges(status=naar)
        )

        assert nieuw is not None and nieuw.status == naar

    @pytest.mark.parametrize("status", ["open", "herinnerd", "geescaleerd", "betaald"])
    async def test_dezelfde_status_opnieuw_zetten_is_geen_overgang(
        self, db_session: AsyncSession, status: str
    ) -> None:
        """Een PATCH die alleen de naam wijzigt en de status ongewijzigd meestuurt, mag niet falen."""
        rij = await _rij_met_status(db_session, 1, status)

        nieuw = await ReceivableRepository(db_session).update(
            1, rij.id, ReceivableChanges(status=status, customer_name="Nieuwe Naam")
        )

        assert nieuw is not None and (nieuw.status, nieuw.customer_name) == (status, "Nieuwe Naam")

    async def test_terug_van_betaald_met_reden_slaagt(self, db_session: AsyncSession) -> None:
        rij = await _rij_met_status(db_session, 1, "betaald")

        nieuw = await ReceivableRepository(db_session).update(
            1, rij.id, ReceivableChanges(status="open", reden="betaling teruggeboekt door de bank")
        )

        assert nieuw is not None and nieuw.status == "open"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAlleenDeKetenZetHerinnerdEnGeescaleerd:
    @pytest.mark.parametrize(("van", "naar"), ALLEEN_DOOR_DE_KETEN)
    async def test_update_weigert_een_status_die_alleen_de_keten_zet(
        self, db_session: AsyncSession, van: str, naar: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, van)

        with pytest.raises(ValueError, match="alleen de keten"):
            await ReceivableRepository(db_session).update(
                1, rij.id, ReceivableChanges(status=naar, reden="betaling teruggeboekt")
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestOngeldigeOvergangen:
    @pytest.mark.parametrize(("van", "naar"), ONGELDIGE_OVERGANGEN)
    async def test_ongeldige_statusovergang_geweigerd(
        self, db_session: AsyncSession, van: str, naar: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, van)

        with pytest.raises(ValueError):
            await ReceivableRepository(db_session).update(1, rij.id, ReceivableChanges(status=naar))

    @pytest.mark.parametrize(("van", "naar"), ONGELDIGE_OVERGANGEN)
    async def test_een_geweigerde_overgang_laat_de_rij_ongemoeid(
        self, db_session: AsyncSession, van: str, naar: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, van)

        with pytest.raises(ValueError):
            await ReceivableRepository(db_session).update(
                1, rij.id, ReceivableChanges(status=naar, customer_name="Mag Niet Blijven")
            )

        herlezen = await ReceivableRepository(db_session).get(1, rij.id)
        assert herlezen is not None and (herlezen.status, herlezen.customer_name) == (
            van,
            "Bakkerij De Korst",
        )

    @pytest.mark.parametrize("naar", TERUG_VAN_BETAALD)
    async def test_terug_van_betaald_zonder_reden_geweigerd(
        self, db_session: AsyncSession, naar: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, "betaald")

        with pytest.raises(ValueError):
            await ReceivableRepository(db_session).update(1, rij.id, ReceivableChanges(status=naar))

    @pytest.mark.parametrize("reden", ["", "   "])
    async def test_een_lege_reden_telt_niet_als_reden(
        self, db_session: AsyncSession, reden: str
    ) -> None:
        rij = await _rij_met_status(db_session, 1, "betaald")

        with pytest.raises(ValueError):
            await ReceivableRepository(db_session).update(
                1, rij.id, ReceivableChanges(status="open", reden=reden)
            )

    async def test_een_onbekende_status_blijft_geweigerd(self, db_session: AsyncSession) -> None:
        rij = await _rij_met_status(db_session, 1, "open")

        with pytest.raises(ValueError):
            await ReceivableRepository(db_session).update(
                1, rij.id, ReceivableChanges(status="kwijtgescholden")
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestGeescaleerdIsEenGeldigeStatus:
    async def test_het_vocabulaire_kent_geescaleerd(self) -> None:
        from src.core.models.receivable_models import RECEIVABLE_STATUSES

        assert "geescaleerd" in RECEIVABLE_STATUSES, (
            f"RECEIVABLE_STATUSES is {RECEIVABLE_STATUSES}; 'geescaleerd' ontbreekt."
        )

    async def test_de_database_laat_geescaleerd_toe(self, db_session: AsyncSession) -> None:
        """De CHECK (`ck_receivables_status`) zelf, niet het Python-vocabulaire.

        De unit-database bouwt de tabel met `create_all` uit het MODEL; de migratie zelf is
        dus hier niet gemeten (dat doet de migratietest van de database-rol).
        """
        rij = await _rij_met_status(db_session, 1, "geescaleerd")

        assert rij.id is not None

    async def test_de_database_blijft_onzin_weigeren(self, db_session: AsyncSession) -> None:
        """Andere kant op: de CHECK is verruimd met EEN waarde, niet weggehaald."""
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await _rij_met_status(db_session, 1, "kwijtgescholden")


@pytest.mark.unit
@pytest.mark.asyncio
class TestTijdstempels:
    async def test_betaald_op_wordt_gezet_bij_de_overgang_naar_betaald(
        self, db_session: AsyncSession
    ) -> None:
        rij = await _rij_met_status(db_session, 1, "herinnerd")
        voor = datetime.now(timezone.utc)

        nieuw = await ReceivableRepository(db_session).update(
            1, rij.id, ReceivableChanges(status="betaald")
        )

        na = datetime.now(timezone.utc)
        assert nieuw is not None
        gezet = _utc(nieuw.betaald_op)
        assert gezet is not None and voor <= gezet <= na, (
            f"betaald_op={nieuw.betaald_op!r}; verwacht tussen {voor} en {na}."
        )

    async def test_betaald_op_blijft_leeg_zolang_er_niet_betaald_is(
        self, db_session: AsyncSession
    ) -> None:
        rij = await _rij_met_status(db_session, 1, "herinnerd")

        nieuw = await ReceivableRepository(db_session).update(
            1, rij.id, ReceivableChanges(customer_name="Nieuwe Naam")
        )

        assert nieuw is not None and nieuw.betaald_op is None

    async def test_een_nieuwe_rij_heeft_geen_herinnerd_op_en_geen_betaald_op(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1)

        rij = await ReceivableRepository(db_session).add(
            1,
            NewReceivable(
                customer_name="K",
                customer_email="k@klant.example",
                invoice_number="N-1",
                amount=Decimal("1.00"),
                due_date=date(2026, 9, 1),
            ),
        )

        assert (rij.herinnerd_op, rij.betaald_op) == (None, None)

    async def test_klaarzetten_van_de_herinnering_zet_herinnerd_op_nog_niet(
        self, db_session: AsyncSession
    ) -> None:
        """`send_payment_reminder` legt alleen een bericht `klaar` neer. `herinnerd_op` zet de
        verzendlus pas na verzending (wfb-dag1 stap 2, test_herinnerd_is_een_feit.py)."""
        from tests.unit.tool_broker.test_receivables_registry import (
            VERSTUREN,
            _brief,
            _registry,
            _seed,
        )

        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag1"}, tenant_id=1
        )

        assert uit["success"] is True
        rij = await ReceivableRepository(db_session).get(1, rid)
        assert rij is not None and (rij.status, rij.herinnerd_op) == ("open", None)

    async def test_een_geweigerde_herinnering_zet_herinnerd_op_niet(
        self, db_session: AsyncSession
    ) -> None:
        """Andere kant op: een betaalde factuur krijgt geen herinnering en dus geen datum."""
        from src.core.models.receivable_models import Receivable
        from tests.unit.tool_broker.test_receivables_registry import (
            VERSTUREN,
            _brief,
            _registry,
            _seed,
        )

        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        rij = await db_session.get(Receivable, rid)
        assert rij is not None
        rij.status = "betaald"
        await db_session.commit()

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag1b"}, tenant_id=1
        )

        await db_session.refresh(rij)
        assert uit["success"] is False and rij.herinnerd_op is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestIsolatieVanDeStatuswijziging:
    async def test_tenant_a_kan_de_status_van_tenant_b_niet_wijzigen(
        self, db_session: AsyncSession
    ) -> None:
        vreemd = await _rij_met_status(db_session, 2, "herinnerd", "B-1")
        await _tenant(db_session, 1)

        uit = await ReceivableRepository(db_session).update(
            1, vreemd.id, ReceivableChanges(status="betaald")
        )

        assert uit is None
        await db_session.refresh(vreemd)
        assert (vreemd.status, vreemd.betaald_op) == ("herinnerd", None)

    async def test_tenant_a_kan_een_vreemde_betaling_ook_niet_terugdraaien(
        self, db_session: AsyncSession
    ) -> None:
        """Ook het pad `betaald -> open met reden` blijft binnen de tenant."""
        vreemd = await _rij_met_status(db_session, 2, "betaald", "B-1")
        await _tenant(db_session, 1)

        uit = await ReceivableRepository(db_session).update(
            1, vreemd.id, ReceivableChanges(status="open", reden="ik wil het zo")
        )

        assert uit is None
        await db_session.refresh(vreemd)
        assert vreemd.status == "betaald"

    async def test_tenant_b_wijzigt_zijn_eigen_rij_wel(self, db_session: AsyncSession) -> None:
        """Zonder deze helft is "weiger alles" een geldige oplossing."""
        eigen = await _rij_met_status(db_session, 2, "herinnerd", "B-1")

        uit = await ReceivableRepository(db_session).update(
            2, eigen.id, ReceivableChanges(status="betaald")
        )

        assert uit is not None and uit.status == "betaald"
