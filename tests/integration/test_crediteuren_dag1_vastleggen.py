"""Crediteuren dag 1 via de API: leveranciers en inkoopfacturen vastleggen, binnen de eigen tenant (Keten F).

Echte app-stack (`register_all_routers`), echte Postgres op netwerkpoort 5455, de echte `require_resource_permission` op het JWT.
Alleen CSRF is vervangen (Redis-gebonden token; de controle zelf heeft eigen tests) en `get_current_user` wijst naar de gezaaide
beheerder van tenant 1. Rechten per rol: `tests/integration/api/test_payables_rechten_per_rol.py`.

De vier rode tests uit de brief (`docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag1-inkoopfacturen-vastleggen.md`):
1. een inkoopfactuur vastleggen en terugvinden in de lijst van de eigen klant;
2. klant B ziet de factuur van klant A niet (en een factuur kan niet naar een leverancier van een ander wijzen);
3. dezelfde factuur van dezelfde leverancier twee keer wordt geweigerd;
4. een niet-toegestane statusovergang geeft een Nederlandse melding.

Wat NIET gemeten wordt: RLS als laatste verdedigingslinie. De app verbindt hier als eigenaar (OP-151), dus het tenantfilter van de
repository trekt de grens; RLS meet `tests/integration/security/test_payables_is_confined_to_its_tenant.py`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/v1/payables"
LEVERANCIERS = f"{URL}/suppliers"

_FACTUUR: dict[str, Any] = {
    "invoice_number": "INK-2026-001",
    "amount_cents": 125050,
    "currency": "EUR",
    "invoice_date": "2026-10-01",
    "due_date": "2026-10-31",
}


@pytest_asyncio.fixture
async def api(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def _geen_csrf() -> None:
        return None

    overrides = {get_db: _db, api_get_db: _db, validate_csrf_token: _geen_csrf}
    integration_app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=1, email="admin@integration.test", tenant_id=1)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


async def _leverancier(api: AsyncClient, naam: str = "Drukkerij Van Dijk") -> int:
    antwoord = await api.post(LEVERANCIERS, json={"name": naam})
    assert antwoord.status_code == 201, antwoord.text
    return int(antwoord.json()["data"]["id"])


async def _factuur(api: AsyncClient, leverancier: int, **extra: Any) -> Any:
    return await api.post(URL, json={**_FACTUUR, "supplier_id": leverancier, **extra})


async def _leverancier_van_tenant_2(session: AsyncSession) -> int:
    from src.core.models.payable_models import Supplier

    rij = Supplier(tenant_id=2, name="Geheime leverancier van tenant twee")
    session.add(rij)
    await session.flush()
    return rij.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestVastleggenEnTerugvinden:
    async def test_a_supplier_is_created_and_listed(self, api: AsyncClient) -> None:
        antwoord = await api.post(
            LEVERANCIERS,
            json={
                "name": "Kantoorhuis BV",
                "iban": "NL91 ABNA 0417 1643 00",
                "email": "info@kantoorhuis.example",
            },
        )

        assert antwoord.status_code == 201, antwoord.text
        data = antwoord.json()["data"]
        assert (data["name"], data["iban"]) == ("Kantoorhuis BV", "NL91ABNA0417164300")
        lijst = (await api.get(LEVERANCIERS)).json()["data"]
        assert [r["name"] for r in lijst] == ["Kantoorhuis BV"]

    async def test_a_payable_is_created_and_found_in_the_list_of_the_own_tenant(
        self, api: AsyncClient
    ) -> None:
        leverancier = await _leverancier(api)

        antwoord = await _factuur(api, leverancier)

        assert antwoord.status_code == 201, antwoord.text
        data = antwoord.json()["data"]
        assert (data["invoice_number"], data["status"], data["amount_cents"]) == (
            "INK-2026-001",
            "ontvangen",
            125050,
        )
        lijst = (await api.get(URL)).json()["data"]
        assert [(r["invoice_number"], r["supplier_name"]) for r in lijst] == [
            ("INK-2026-001", "Drukkerij Van Dijk")
        ]

    async def test_the_list_is_paginated_and_can_filter_on_status(self, api: AsyncClient) -> None:
        leverancier = await _leverancier(api)
        for i in range(3):
            await _factuur(api, leverancier, invoice_number=f"P-{i}")

        pagina = (await api.get(URL, params={"limit": 2, "offset": 1})).json()
        gecontroleerd = (await api.get(URL, params={"status": "gecontroleerd"})).json()["data"]

        assert (len(pagina["data"]), pagina["limit"], pagina["offset"]) == (2, 2, 1)
        assert gecontroleerd == []

    async def test_a_tenant_id_in_the_body_is_refused(self, api: AsyncClient) -> None:
        leverancier = await _leverancier(api)

        antwoord = await _factuur(api, leverancier, tenant_id=2)

        assert antwoord.status_code == 422

    async def test_a_float_amount_is_refused(self, api: AsyncClient) -> None:
        """Geld is een geheel aantal centen; een komma-getal of tekst is geen bedrag."""
        leverancier = await _leverancier(api)

        assert (await _factuur(api, leverancier, amount_cents=12.5)).status_code == 422
        assert (await _factuur(api, leverancier, amount_cents="100")).status_code == 422

    async def test_a_zero_amount_is_refused_with_a_dutch_message(self, api: AsyncClient) -> None:
        leverancier = await _leverancier(api)

        antwoord = await _factuur(api, leverancier, amount_cents=0)

        assert antwoord.status_code == 409
        assert antwoord.json()["detail"] == "Het bedrag moet groter zijn dan nul."

    async def test_an_invalid_iban_is_refused_with_a_dutch_message(self, api: AsyncClient) -> None:
        antwoord = await api.post(
            LEVERANCIERS, json={"name": "Fout IBAN", "iban": "NL91ABNA0417164301"}
        )

        assert antwoord.status_code == 409
        assert "IBAN" in antwoord.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeenDubbeleFactuur:
    async def test_the_same_invoice_of_the_same_supplier_twice_is_refused_in_dutch(
        self, api: AsyncClient
    ) -> None:
        leverancier = await _leverancier(api)
        assert (await _factuur(api, leverancier)).status_code == 201

        tweede = await _factuur(api, leverancier)

        assert tweede.status_code == 409
        assert tweede.json()["detail"] == "Deze factuur van deze leverancier is al vastgelegd."

    async def test_the_same_invoice_number_of_another_supplier_is_allowed(
        self, api: AsyncClient
    ) -> None:
        een = await _leverancier(api, "Een BV")
        twee = await _leverancier(api, "Twee BV")
        assert (await _factuur(api, een)).status_code == 201

        assert (await _factuur(api, twee)).status_code == 201

    async def test_the_same_supplier_name_twice_is_refused_in_dutch(self, api: AsyncClient) -> None:
        await _leverancier(api, "Dubbel BV")

        tweede = await api.post(LEVERANCIERS, json={"name": "Dubbel BV"})

        assert tweede.status_code == 409
        assert tweede.json()["detail"] == "Er bestaat al een leverancier met deze naam."


@pytest.mark.integration
@pytest.mark.asyncio
class TestIsolatie:
    """Beide richtingen: tenant 1 ziet de rij van tenant 2 niet, zijn eigen wel. Zonder de tweede helft is "alles weigeren" goed."""

    async def test_tenant_1_does_not_see_the_supplier_of_tenant_2(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _leverancier_van_tenant_2(postgres_session)
        await _leverancier(api, "Eigen leverancier")

        namen = [r["name"] for r in (await api.get(LEVERANCIERS)).json()["data"]]

        assert namen == ["Eigen leverancier"]

    async def test_tenant_1_does_not_see_the_payable_of_tenant_2(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        from datetime import date

        from src.core.models.payable_models import Payable

        vreemd = await _leverancier_van_tenant_2(postgres_session)
        postgres_session.add(
            Payable(
                tenant_id=2,
                supplier_id=vreemd,
                invoice_number="B-999",
                amount_cents=100,
                currency="EUR",
                invoice_date=date(2026, 10, 1),
                due_date=date(2026, 10, 31),
                status="ontvangen",
            )
        )
        await postgres_session.flush()
        eigen = await _leverancier(api)
        await _factuur(api, eigen)

        nummers = [r["invoice_number"] for r in (await api.get(URL)).json()["data"]]

        assert nummers == ["INK-2026-001"]

    async def test_a_payable_cannot_point_to_a_supplier_of_another_tenant(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        vreemd = await _leverancier_van_tenant_2(postgres_session)

        antwoord = await _factuur(api, vreemd)

        assert antwoord.status_code == 409
        assert antwoord.json()["detail"] == "Deze leverancier bestaat niet."

    async def test_tenant_1_cannot_check_the_payable_of_tenant_2(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        from datetime import date

        from src.core.models.payable_models import Payable

        vreemd = await _leverancier_van_tenant_2(postgres_session)
        rij = Payable(
            tenant_id=2,
            supplier_id=vreemd,
            invoice_number="B-998",
            amount_cents=100,
            currency="EUR",
            invoice_date=date(2026, 10, 1),
            due_date=date(2026, 10, 31),
            status="ontvangen",
        )
        postgres_session.add(rij)
        await postgres_session.flush()

        antwoord = await api.patch(f"{URL}/{rij.id}", json={"status": "gecontroleerd"})

        assert antwoord.status_code == 404
        assert rij.status == "ontvangen"


@pytest.mark.integration
@pytest.mark.asyncio
class TestStatusverloop:
    async def test_a_received_payable_can_be_checked_and_records_who_and_when(
        self, api: AsyncClient
    ) -> None:
        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]

        antwoord = await api.patch(f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"})

        assert antwoord.status_code == 200, antwoord.text
        data = antwoord.json()["data"]
        assert data["status"] == "gecontroleerd" and data["checked_at"] is not None

    async def test_checking_twice_is_refused_in_dutch(self, api: AsyncClient) -> None:
        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]
        await api.patch(f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"})

        tweede = await api.patch(f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"})

        assert tweede.status_code == 409
        assert (
            tweede.json()["detail"]
            == "De status kan niet van 'gecontroleerd' naar 'gecontroleerd' worden gezet."
        )

    @pytest.mark.parametrize("naar", ["goedgekeurd", "in_betaalbestand", "betaald", "afgewezen"])
    async def test_a_later_step_says_in_dutch_that_it_is_not_available_yet(
        self, api: AsyncClient, naar: str
    ) -> None:
        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]

        antwoord = await api.patch(f"{URL}/{factuur['id']}", json={"status": naar})

        assert antwoord.status_code == 409
        assert "latere stap" in antwoord.json()["detail"]

    async def test_an_unknown_status_is_refused_in_dutch_without_internal_text(
        self, api: AsyncClient
    ) -> None:
        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]

        antwoord = await api.patch(f"{URL}/{factuur['id']}", json={"status": "bestaat_niet"})

        assert antwoord.status_code == 409
        assert antwoord.json()["detail"] == "Onbekende status: 'bestaat_niet'."

    async def test_a_missing_payable_is_a_404(self, api: AsyncClient) -> None:
        antwoord = await api.patch(f"{URL}/999999", json={"status": "gecontroleerd"})

        assert antwoord.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenFalendeAuditregelBlokkeertNiets:
    """Backend-patterns par. 3: de primaire gegevens eerst, de auditregel daarna in `best_effort`. Een auditregel die faalt mag de
    klant geen fout geven voor iets dat WEL is vastgelegd (Gate 2: na de rollback van `best_effort` kan het antwoord niet meer uit
    een verlopen rij worden opgebouwd, en een nieuwe poging geeft dan "al vastgelegd")."""

    @pytest.fixture
    def audit_faalt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        audit = importlib.import_module("src.core.governance.services.audit_service").AuditService

        async def _faalt(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("de auditketen is niet beschikbaar")

        monkeypatch.setattr(audit, "log_event", _faalt)

    async def test_a_supplier_is_still_created(self, api: AsyncClient, audit_faalt: None) -> None:
        antwoord = await api.post(LEVERANCIERS, json={"name": "Zonder audit BV"})

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["data"]["name"] == "Zonder audit BV"

    async def test_a_payable_is_still_created_with_its_supplier_name(self, api: AsyncClient, audit_faalt: None) -> None:
        leverancier = await _leverancier(api)

        antwoord = await _factuur(api, leverancier)

        assert antwoord.status_code == 201, antwoord.text
        data = antwoord.json()["data"]
        assert (data["invoice_number"], data["supplier_name"]) == ("INK-2026-001", "Drukkerij Van Dijk")

    async def test_the_payable_is_in_the_list_afterwards(self, api: AsyncClient, audit_faalt: None) -> None:
        await _factuur(api, await _leverancier(api))

        nummers = [r["invoice_number"] for r in (await api.get(URL)).json()["data"]]

        assert nummers == ["INK-2026-001"]

    async def test_checking_a_payable_still_works(self, api: AsyncClient, audit_faalt: None) -> None:
        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]

        antwoord = await api.patch(f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"})

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"]["status"] == "gecontroleerd"


@pytest.mark.integration
@pytest.mark.asyncio
class TestInvoerWordtSchoongemaakt:
    async def test_spaces_around_a_name_and_an_invoice_number_are_removed(self, api: AsyncClient) -> None:
        leverancier = await api.post(LEVERANCIERS, json={"name": "  Trim BV  "})
        assert leverancier.json()["data"]["name"] == "Trim BV"

        factuur = await _factuur(api, leverancier.json()["data"]["id"], invoice_number="  INK-TRIM  ")

        assert factuur.json()["data"]["invoice_number"] == "INK-TRIM"

    async def test_a_name_that_differs_only_in_case_is_a_duplicate(self, api: AsyncClient) -> None:
        await _leverancier(api, "Acme BV")

        tweede = await api.post(LEVERANCIERS, json={"name": "ACME bv"})

        assert tweede.status_code == 409
        assert tweede.json()["detail"] == "Er bestaat al een leverancier met deze naam."

    async def test_an_invoice_number_that_differs_only_in_case_is_a_duplicate(self, api: AsyncClient) -> None:
        leverancier = await _leverancier(api)
        await _factuur(api, leverancier, invoice_number="INK-1")

        tweede = await _factuur(api, leverancier, invoice_number="ink-1")

        assert tweede.status_code == 409
        assert tweede.json()["detail"] == "Deze factuur van deze leverancier is al vastgelegd."

    @pytest.mark.parametrize(
        "teken",
        ["\u2028", "\u2029", "\u0085", "\u202e", "\u2066", "\u200b", "\n", "\r", "\t", "\x00"],
        ids=["lijnscheider", "alineascheider", "volgende-regel", "bidi-omkering", "bidi-isolatie", "nulbreed", "lf", "cr", "tab", "nul"],
    )
    async def test_invisible_and_line_breaking_characters_are_refused_in_a_name_and_an_invoice_number(
        self, api: AsyncClient, teken: str
    ) -> None:
        """Gate 2: zo'n teken verbergt of verdraait tekst in een scherm, brief of betaalbestand (dag 4)."""
        leverancier = await _leverancier(api)

        naam = await api.post(LEVERANCIERS, json={"name": f"Slecht{teken}BV"})
        nummer = await _factuur(api, leverancier, invoice_number=f"INK{teken}1")

        assert (naam.status_code, nummer.status_code) == (422, 422)

    async def test_a_name_of_only_spaces_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(LEVERANCIERS, json={"name": "    "})

        assert antwoord.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestStatusWijzigingIsVergrendeld:
    async def test_changing_the_status_reads_the_row_with_a_lock(self, api: AsyncClient) -> None:
        """Gate 2: twee gelijktijdige PATCH's lazen allebei `ontvangen` en schreven allebei; nu wacht de tweede op de eerste."""
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        factuur = (await _factuur(api, await _leverancier(api))).json()["data"]
        statements: list[str] = []

        def _vang(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            statements.append(statement)

        event.listen(Engine, "before_cursor_execute", _vang)
        try:
            antwoord = await api.patch(f"{URL}/{factuur['id']}", json={"status": "gecontroleerd"})
        finally:
            event.remove(Engine, "before_cursor_execute", _vang)

        assert antwoord.status_code == 200, antwoord.text
        assert any("FOR UPDATE" in s and "payables" in s for s in statements), statements
