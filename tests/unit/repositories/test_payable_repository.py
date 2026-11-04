"""`SupplierRepository` en `PayableRepository` -- crediteuren dag 1 (inkoopfacturen en leveranciers vastleggen).

Echte database-sessie, geen mocks: alleen een echte query tegen rijen van twee tenants bewijst de isolatie. Zelfde opstelling
als `test_receivable_repository.py`: de globale tenantfilter staat uit, dus het EIGEN filter van de repository levert de
isolatie, en dat is wat deze module meet. RLS als tweede laag meet
`tests/integration/security/test_payables_is_confined_to_its_tenant.py`.

Elke repositorymethode heeft een isolatietest (backend-patterns par. 11): `add`, `get`, `list_for_tenant` en `set_status` voor
beide repositories.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau: `create_all` ziet alleen wat op dat moment in de metadata staat.
import src.core.database.import_all_models  # noqa: F401
from src.core.exceptions import ValidatieFout
from src.core.models.rbac_models import Tenant
from src.core.repositories.payable_repository import (
    NewPayable,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
)

GELDIG_IBAN = "NL91ABNA0417164300"


async def _tenant(session: AsyncSession, tenant_id: int, slug: str) -> None:
    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()


async def _leverancier(
    session: AsyncSession, tenant_id: int, naam: str = "Drukkerij Van Dijk"
) -> int:
    rij = await SupplierRepository(session).add(tenant_id, NewSupplier(name=naam))
    return rij.id


def _factuur(leverancier_id: int, nummer: str = "INK-001", **extra: object) -> NewPayable:
    velden: dict[str, object] = {
        "supplier_id": leverancier_id,
        "invoice_number": nummer,
        "amount_cents": 125050,
        "currency": "EUR",
        "invoice_date": date(2026, 10, 1),
        "due_date": date(2026, 10, 31),
    }
    velden.update(extra)
    return NewPayable(**velden)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
class TestSupplierTenantIsolation:
    async def test_add_writes_under_the_given_tenant(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")

        rij = await SupplierRepository(db_session).add(2, NewSupplier(name="B-leverancier"))

        assert rij.tenant_id == 2

    async def test_get_does_not_find_a_supplier_of_another_tenant(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = SupplierRepository(db_session)
        vreemd = await repo.add(2, NewSupplier(name="B-leverancier"))

        assert await repo.get(1, vreemd.id) is None
        eigen = await repo.get(2, vreemd.id)
        assert eigen is not None and eigen.name == "B-leverancier", (
            "De eigen tenant vindt zijn rij niet terug: dan bewijst de weigering hierboven niets."
        )

    async def test_list_shows_only_the_own_suppliers(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="A-leverancier"))
        await repo.add(2, NewSupplier(name="B-leverancier"))

        namen = {r.name for r in await repo.list_for_tenant(1)}

        assert namen == {"A-leverancier"}

    async def test_the_same_name_is_allowed_under_another_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """De unieke naam is per tenant, niet globaal."""
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Dezelfde BV"))

        rij = await repo.add(2, NewSupplier(name="Dezelfde BV"))

        assert rij.tenant_id == 2

    def test_the_input_has_no_tenant_field(self) -> None:
        assert "tenant_id" not in {f.name for f in dataclasses.fields(NewSupplier)}


@pytest.mark.unit
@pytest.mark.asyncio
class TestSupplierValidation:
    async def test_the_same_name_twice_under_one_tenant_is_refused_in_dutch(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Drukkerij Van Dijk"))

        with pytest.raises(ValidatieFout, match="al een leverancier"):
            await repo.add(1, NewSupplier(name="Drukkerij Van Dijk"))

    async def test_a_valid_iban_is_stored_without_spaces_in_capitals(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await SupplierRepository(db_session).add(
            1, NewSupplier(name="Met IBAN", iban="nl91 abna 0417 1643 00")
        )

        assert rij.iban == GELDIG_IBAN

    @pytest.mark.parametrize(
        "iban", ["NL91ABNA0417164301", "12345", "NL91 ABNA", "NLXXABNA0417164300"]
    )
    async def test_an_invalid_iban_is_refused_in_dutch(
        self, db_session: AsyncSession, iban: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")

        with pytest.raises(ValidatieFout, match="IBAN"):
            await SupplierRepository(db_session).add(1, NewSupplier(name="Fout IBAN", iban=iban))

    async def test_a_supplier_without_an_iban_is_allowed(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await SupplierRepository(db_session).add(1, NewSupplier(name="Zonder IBAN"))

        assert rij.iban is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestPayableTenantIsolation:
    async def test_add_writes_under_the_given_tenant(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        leverancier = await _leverancier(db_session, 2)

        rij = await PayableRepository(db_session).add(2, _factuur(leverancier), created_by=None)

        assert rij.tenant_id == 2

    async def test_add_refuses_a_supplier_of_another_tenant(self, db_session: AsyncSession) -> None:
        """Een factuur van tenant 1 mag niet naar een leverancier van tenant 2 wijzen."""
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        vreemde_leverancier = await _leverancier(db_session, 2)

        with pytest.raises(ValidatieFout, match="leverancier bestaat niet"):
            await PayableRepository(db_session).add(
                1, _factuur(vreemde_leverancier), created_by=None
            )

    async def test_get_does_not_find_a_payable_of_another_tenant(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = PayableRepository(db_session)
        vreemd = await repo.add(2, _factuur(await _leverancier(db_session, 2)), created_by=None)

        assert await repo.get(1, vreemd.id) is None
        eigen = await repo.get(2, vreemd.id)
        assert eigen is not None and eigen.invoice_number == "INK-001", (
            "De eigen tenant vindt zijn rij niet terug: dan bewijst de weigering hierboven niets."
        )

    async def test_list_shows_only_the_own_payables(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = PayableRepository(db_session)
        await repo.add(1, _factuur(await _leverancier(db_session, 1), "A-001"), created_by=None)
        await repo.add(2, _factuur(await _leverancier(db_session, 2), "B-001"), created_by=None)

        nummers = {r.invoice_number for r in await repo.list_for_tenant(1)}

        assert nummers == {"A-001"}

    async def test_list_carries_the_supplier_name(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        await repo.add(
            1, _factuur(await _leverancier(db_session, 1, "Kantoorhuis")), created_by=None
        )

        rijen = await repo.list_for_tenant(1)

        assert [r.supplier.name for r in rijen] == ["Kantoorhuis"]

    async def test_list_is_paginated_and_filters_on_status(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        leverancier = await _leverancier(db_session, 1)
        for i in range(3):
            await repo.add(1, _factuur(leverancier, f"P-{i}"), created_by=None)
        await repo.set_status(1, (await repo.list_for_tenant(1))[0].id, "gecontroleerd", door=7)

        pagina = await repo.list_for_tenant(1, limit=2, offset=0)
        gecontroleerd = await repo.list_for_tenant(1, status="gecontroleerd")

        assert len(pagina) == 2 and [r.status for r in gecontroleerd] == ["gecontroleerd"]

    async def test_set_status_does_not_touch_a_payable_of_another_tenant(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        await _tenant(db_session, 2, "crd-b")
        repo = PayableRepository(db_session)
        vreemd = await repo.add(2, _factuur(await _leverancier(db_session, 2)), created_by=None)

        resultaat = await repo.set_status(1, vreemd.id, "gecontroleerd", door=7)

        assert resultaat is None
        assert (await repo.get(2, vreemd.id)).status == "ontvangen"  # type: ignore[union-attr]

    def test_the_input_has_no_tenant_field(self) -> None:
        assert "tenant_id" not in {f.name for f in dataclasses.fields(NewPayable)}


@pytest.mark.unit
@pytest.mark.asyncio
class TestPayableValidation:
    async def test_a_new_payable_is_received_and_records_who_created_it(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await PayableRepository(db_session).add(
            1, _factuur(await _leverancier(db_session, 1)), created_by=None
        )

        assert (rij.status, rij.currency, rij.checked_at) == ("ontvangen", "EUR", None)

    async def test_a_new_payable_records_the_user_who_created_it(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await PayableRepository(db_session).add(
            1, _factuur(await _leverancier(db_session, 1)), created_by=42
        )

        assert rij.created_by_user_id == 42

    async def test_the_same_invoice_of_the_same_supplier_twice_is_refused_in_dutch(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        leverancier = await _leverancier(db_session, 1)
        await repo.add(1, _factuur(leverancier, "INK-9"), created_by=None)

        with pytest.raises(ValidatieFout, match="al vastgelegd"):
            await repo.add(1, _factuur(leverancier, "INK-9"), created_by=None)

    async def test_the_same_invoice_number_of_another_supplier_is_allowed(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        await repo.add(
            1, _factuur(await _leverancier(db_session, 1, "Een BV"), "INK-9"), created_by=None
        )

        rij = await repo.add(
            1, _factuur(await _leverancier(db_session, 1, "Twee BV"), "INK-9"), created_by=None
        )

        assert rij.invoice_number == "INK-9"

    async def test_a_refused_duplicate_leaves_the_session_usable(
        self, db_session: AsyncSession
    ) -> None:
        """Na de weigering moet de sessie door kunnen: de API doet daarna nog een commit of een audit-regel."""
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        leverancier = await _leverancier(db_session, 1)
        await repo.add(1, _factuur(leverancier, "INK-9"), created_by=None)
        with pytest.raises(ValidatieFout):
            await repo.add(1, _factuur(leverancier, "INK-9"), created_by=None)

        rij = await repo.add(1, _factuur(leverancier, "INK-10"), created_by=None)

        assert rij.invoice_number == "INK-10"

    @pytest.mark.parametrize("bedrag", [0, -1])
    async def test_a_bad_amount_is_refused_in_dutch(
        self, db_session: AsyncSession, bedrag: int
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        leverancier = await _leverancier(db_session, 1)

        with pytest.raises(ValidatieFout, match="groter zijn dan nul"):
            await PayableRepository(db_session).add(
                1, _factuur(leverancier, amount_cents=bedrag), created_by=None
            )

    @pytest.mark.parametrize("bedrag", [12.5, True, "100"])
    async def test_an_amount_that_is_not_an_integer_is_a_programming_error(
        self, db_session: AsyncSession, bedrag: object
    ) -> None:
        """Geld is een geheel aantal centen, nooit een float; zo'n waarde is een fout in de aanroeper, geen invoerfout."""
        await _tenant(db_session, 1, "crd-a")
        leverancier = await _leverancier(db_session, 1)

        with pytest.raises(TypeError):
            await PayableRepository(db_session).add(
                1, _factuur(leverancier, amount_cents=bedrag), created_by=None
            )

    async def test_a_lowercase_currency_is_refused_in_dutch(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        leverancier = await _leverancier(db_session, 1)

        with pytest.raises(ValidatieFout, match="drie hoofdletters"):
            await PayableRepository(db_session).add(
                1, _factuur(leverancier, currency="eur"), created_by=None
            )

    async def test_a_due_date_before_the_invoice_date_is_refused_in_dutch(
        self, db_session: AsyncSession
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        leverancier = await _leverancier(db_session, 1)

        with pytest.raises(ValidatieFout, match="vervaldatum"):
            await PayableRepository(db_session).add(
                1,
                _factuur(leverancier, invoice_date=date(2026, 10, 10), due_date=date(2026, 10, 1)),
                created_by=None,
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestPayableStatusFlow:
    async def _ontvangen(self, session: AsyncSession) -> tuple[PayableRepository, int]:
        await _tenant(session, 1, "crd-a")
        repo = PayableRepository(session)
        rij = await repo.add(1, _factuur(await _leverancier(session, 1)), created_by=None)
        return repo, rij.id

    async def test_received_can_become_checked_and_records_who_and_when(
        self, db_session: AsyncSession
    ) -> None:
        repo, payable_id = await self._ontvangen(db_session)

        rij = await repo.set_status(1, payable_id, "gecontroleerd", door=42)

        assert rij is not None
        assert (rij.status, rij.checked_by_user_id) == ("gecontroleerd", 42)
        assert rij.checked_at is not None

    async def test_checking_twice_is_refused_in_dutch(self, db_session: AsyncSession) -> None:
        repo, payable_id = await self._ontvangen(db_session)
        await repo.set_status(1, payable_id, "gecontroleerd", door=42)

        with pytest.raises(
            ValidatieFout, match="kan niet van 'gecontroleerd' naar 'gecontroleerd'"
        ):
            await repo.set_status(1, payable_id, "gecontroleerd", door=42)

    @pytest.mark.parametrize("naar", ["goedgekeurd", "in_betaalbestand", "betaald"])
    async def test_later_steps_are_not_available_yet_and_say_so_in_dutch(
        self, db_session: AsyncSession, naar: str
    ) -> None:
        """Goedkeuren, het betaalbestand en afboeken zijn dag 3 en 4; dag 1 mag ze niet zetten."""
        repo, payable_id = await self._ontvangen(db_session)

        with pytest.raises(ValidatieFout, match="latere stap"):
            await repo.set_status(1, payable_id, naar, door=42)

    async def test_an_unknown_status_is_refused_in_dutch(self, db_session: AsyncSession) -> None:
        repo, payable_id = await self._ontvangen(db_session)

        with pytest.raises(ValidatieFout, match="Onbekende status"):
            await repo.set_status(1, payable_id, "bestaat_niet", door=42)

    async def test_a_refused_step_leaves_the_status_alone(self, db_session: AsyncSession) -> None:
        repo, payable_id = await self._ontvangen(db_session)
        with pytest.raises(ValidatieFout):
            await repo.set_status(1, payable_id, "betaald", door=42)

        assert (await repo.get(1, payable_id)).status == "ontvangen"  # type: ignore[union-attr]


def _iban_met_controlecijfers(land: str, bban: str) -> str:
    """Een IBAN met kloppende controlesom (modulo 97) voor een BBAN van elke lengte, om de lengte los van de som te toetsen."""
    getal = "".join(str(int(teken, 36)) for teken in bban + land + "00")
    return f"{land}{98 - int(getal) % 97:02d}{bban}"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGelijkeNamenEnNummersZijnDubbel:
    """Gate 2: "Acme BV", "acme bv" en "Acme BV " zijn voor een mens een leverancier, en "INK-1" en "ink-1 " een factuur. Dubbel
    betalen is het echte risico van crediteuren; de controle mag dus niet op de exacte tekst rusten."""

    @pytest.mark.parametrize("tweede", ["acme bv", "ACME BV", "  Acme BV  ", "Acme bv"])
    async def test_a_supplier_that_differs_in_case_or_spaces_is_a_duplicate(
        self, db_session: AsyncSession, tweede: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = SupplierRepository(db_session)
        await repo.add(1, NewSupplier(name="Acme BV"))

        with pytest.raises(ValidatieFout, match="al een leverancier"):
            await repo.add(1, NewSupplier(name=tweede))

    async def test_the_stored_name_has_no_spaces_around_it(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await SupplierRepository(db_session).add(1, NewSupplier(name="  Acme BV  "))

        assert rij.name == "Acme BV"

    @pytest.mark.parametrize("tweede", ["ink-1", "INK-1 ", " Ink-1"])
    async def test_an_invoice_number_that_differs_in_case_or_spaces_is_a_duplicate(
        self, db_session: AsyncSession, tweede: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        leverancier = await _leverancier(db_session, 1)
        await repo.add(1, _factuur(leverancier, "INK-1"), created_by=None)

        with pytest.raises(ValidatieFout, match="al vastgelegd"):
            await repo.add(1, _factuur(leverancier, tweede), created_by=None)

    async def test_the_stored_invoice_number_has_no_spaces_around_it(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await PayableRepository(db_session).add(
            1, _factuur(await _leverancier(db_session, 1), " INK-7 "), created_by=None
        )

        assert rij.invoice_number == "INK-7"

    async def test_the_same_number_in_another_case_is_allowed_for_another_supplier(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        await repo.add(1, _factuur(await _leverancier(db_session, 1, "Een BV"), "INK-1"), created_by=None)

        rij = await repo.add(1, _factuur(await _leverancier(db_session, 1, "Twee BV"), "ink-1"), created_by=None)

        assert rij.invoice_number == "ink-1"


@pytest.mark.unit
@pytest.mark.asyncio
class TestIbanLengte:
    """Een IBAN met kloppende som maar de verkeerde lengte voor het land komt er niet in (Gate 2): bij een typefout is de kans
    1 op 97 dat de som toevallig klopt, en een betaalbestand mag dan niet naar een onbestaand nummer gaan."""

    async def test_a_dutch_iban_of_the_right_length_is_accepted(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, 1, "crd-a")

        rij = await SupplierRepository(db_session).add(
            1, NewSupplier(name="Goed", iban=_iban_met_controlecijfers("NL", "ABNA0417164300"))
        )

        assert rij.iban is not None and len(rij.iban) == 18

    @pytest.mark.parametrize("bban", ["ABNA041716430", "ABNA04171643000"])
    async def test_a_dutch_iban_of_the_wrong_length_with_a_valid_checksum_is_refused(
        self, db_session: AsyncSession, bban: str
    ) -> None:
        await _tenant(db_session, 1, "crd-a")

        with pytest.raises(ValidatieFout, match="IBAN"):
            await SupplierRepository(db_session).add(
                1, NewSupplier(name="Fout", iban=_iban_met_controlecijfers("NL", bban))
            )

    async def test_a_country_we_do_not_know_is_accepted_when_the_checksum_is_valid(self, db_session: AsyncSession) -> None:
        """Buiten de SEPA-landen kennen we de lengte niet; dag 4 filtert op SEPA voor het betaalbestand."""
        await _tenant(db_session, 1, "crd-a")

        rij = await SupplierRepository(db_session).add(
            1, NewSupplier(name="Ver weg", iban=_iban_met_controlecijfers("BR", "00360305000010009795493C1"))
        )

        assert rij.iban is not None and rij.iban.startswith("BR")


@pytest.mark.unit
@pytest.mark.asyncio
class TestKleinePunten:
    async def test_received_to_received_says_it_cannot_be_set_not_that_it_comes_later(
        self, db_session: AsyncSession
    ) -> None:
        """Gate 2: `ontvangen` is geen latere stap; de tekst "hoort bij een latere stap" zou verwarren."""
        await _tenant(db_session, 1, "crd-a")
        repo = PayableRepository(db_session)
        rij = await repo.add(1, _factuur(await _leverancier(db_session, 1)), created_by=None)

        with pytest.raises(ValidatieFout, match="kan niet van 'ontvangen' naar 'ontvangen'"):
            await repo.set_status(1, rij.id, "ontvangen", door=1)

    @pytest.mark.parametrize("repository", ["leverancier", "factuur"])
    async def test_an_integrity_error_that_is_not_a_duplicate_is_not_reported_as_one(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, repository: str
    ) -> None:
        """Gate 2: een sleutel- of CHECK-fout mag de klant niet "al vastgelegd" noemen; zo'n fout is een programmeerfout."""
        await _tenant(db_session, 1, "crd-a")
        leverancier = await _leverancier(db_session, 1)

        async def _flush(*args: object, **kwargs: object) -> None:
            raise IntegrityError("INSERT", {}, Exception('violates foreign key constraint "fk_payables_tenant_supplier"'))

        monkeypatch.setattr(db_session, "flush", _flush)

        with pytest.raises(IntegrityError):
            if repository == "leverancier":
                await SupplierRepository(db_session).add(1, NewSupplier(name="Nieuw"))
            else:
                await PayableRepository(db_session).add(1, _factuur(leverancier, "NIEUW-1"), created_by=None)
