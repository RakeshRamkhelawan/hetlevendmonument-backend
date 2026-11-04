"""Crediteuren dag 2: de crediteurenagent verwerkt een gelezen inkoopfactuur zelf (Keten F, agent-first).

Brief `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag2-de-agent-verwerkt-de-factuur.md`. De agent doet het werk; een
mens keurt alleen goed wat geld of een relatie raakt:

1. een gelezen upload van een bekende leverancier wordt zonder klik een inkoopfactuur `ontvangen`;
2. een afwijkend IBAN geeft een ticket met waarschuwing: geen factuur, het IBAN van de leverancier blijft gelijk;
3. een onbekende leverancier geeft een ticket; na goedkeuren bestaan de leverancier en de factuur;
4. afwijzen vraagt een reden; met reden komt er geen factuur;
5. een dubbele factuur geeft geen tweede factuur en geen ticket, wel een Nederlandse reden in het logboek;
6. een andere tenant ziet het ticket en de factuur niet;
7. aanpassen gaat via de bevestigroute, met reden, en sluit het ticket.

**Wat echt is en wat niet** (zelfde als `scenarios/test_scenario_5_betalingsherinnering.py`): echt zijn Postgres op netwerkpoort 5455, de
Council, de HITL-vloer en het ticket in `hitl_tickets`, de HITL-routes, de broker met zijn verzilvering, de registry en de auditketen.
Vervangen zijn de bonlezer-worker (een nepworker die meldt wat de echte zou melden, inclusief de sha256 van de bytes), `get_current_user`
en de CSRF-controle. `db_manager` en geen `postgres_session`: agent, Council en registry openen eigen sessies, dus hier wordt echt
gecommit en na elke test opgeruimd.

Wat NIET gemeten wordt: het lezen van een echte PDF (OCR; de acceptatie doet dat) en een draaiend scherm.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401

TENANT = 1
INITIATOR = 1
ANDERE_TENANT = 2
_PDF = b"%PDF-1.4 een verzonnen factuur"
_IBAN = "NL91ABNA0417164300"
_ANDER_IBAN = "NL02ABNA0123456789"

_GELEZEN: dict[str, object] = {
    "leverancier": "Drukkerij Van Dijk BV",
    "datum": "2026-10-01",
    "totaal": "1210.00",
    "factuurnummer": "INK-2026-0042",
    "btw": {"21": "210.00"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
    "iban": _IBAN,
    "vervaldatum": "2026-10-31",
    "valuta": "EUR",
}


class _NepWorker:
    """Wat de echte worker zou melden, zonder Redis: `verstuur` onthoudt het bestand, `haal` leest het en hasht het."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.velden: dict[str, object] = dict(_GELEZEN)
        self.klaar = True
        self._verstuurd: dict[str, tuple[int, str]] = {}

    def verstuur(self, tenant_id: int, bestand_id: str) -> str:
        self._verstuurd[bestand_id] = (tenant_id, bestand_id)
        return bestand_id

    def haal(self, message_id: str) -> dict[str, object]:
        from dramatiq.results import ResultMissing

        if not self.klaar:
            raise ResultMissing("nog niet klaar")
        tenant_id, bestand_id = self._verstuurd[message_id]
        inhoud = (self.root / str(tenant_id) / bestand_id).read_bytes()
        return {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(inhoud).hexdigest(),
            "velden": dict(self.velden),
        }

    def dienst(self) -> Any:
        from src.core.als.bonlezer.upload import BonDienst

        return BonDienst(self.root, verstuur=self.verstuur, haal=self.haal)


#: De nepworker van de lopende test; `_pas_aan` en de fixture delen hem.
_AKTIEF: list[_NepWorker] = []


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    nep = _NepWorker(tmp_path)
    monkeypatch.setattr("src.core.tool_broker.payables_registry._bon_dienst", nep.dienst)
    _AKTIEF.append(nep)
    yield nep
    _AKTIEF.clear()


@pytest_asyncio.fixture(autouse=True)
async def _opruimen(goedkeurder_gebruikers: None) -> AsyncGenerator[None, None]:
    yield
    await _sql("DELETE FROM payables WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM suppliers WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    await _sql("DELETE FROM hitl_tickets WHERE tenant_id = :t", t=TENANT)


async def _leverancier(naam: str = "Drukkerij Van Dijk BV", iban: str | None = _IBAN) -> int:
    from src.core.database.database import db_manager
    from src.core.repositories.payable_repository import NewSupplier, SupplierRepository

    async with db_manager.get_session() as session:
        rij = await SupplierRepository(session).add(TENANT, NewSupplier(name=naam, iban=iban))
        await session.commit()
        return int(rij.id)


async def _verwerk(bestand_id: str, *, door: int | None = INITIATOR) -> dict[str, Any]:
    from src.core.als.agents.loader import EnterpriseCatalogLoader

    agent = EnterpriseCatalogLoader().load_all().get_agent_instance("crediteuren", TENANT)
    return dict(await agent.verwerk_upload(bestand_id, initiated_by_user_id=door))


def _upload(worker: _NepWorker) -> str:
    return str(worker.dienst().uploaden(TENANT, "factuur.pdf", _PDF, "factuur"))


async def _facturen() -> list[tuple[Any, ...]]:
    rijen = await _sql(
        "SELECT invoice_number, status, supplier_id FROM payables WHERE tenant_id = :t ORDER BY id",
        t=TENANT,
    )
    return [tuple(r) for r in rijen.all()]


async def _leveranciers() -> list[tuple[Any, ...]]:
    rijen = await _sql(
        "SELECT name, iban FROM suppliers WHERE tenant_id = :t ORDER BY id", t=TENANT
    )
    return [tuple(r) for r in rijen.all()]


async def _tickets() -> list[str]:
    rijen = await _sql(
        "SELECT ticket_ref FROM hitl_tickets WHERE tenant_id = :t ORDER BY id", t=TENANT
    )
    return [r[0] for r in rijen.all()]


async def _ticket_payload(ref: str) -> dict[str, Any]:
    rij = (await _sql("SELECT payload FROM hitl_tickets WHERE ticket_ref = :r", r=ref)).one()
    return dict(rij[0])


async def _audit(event_type: str) -> list[Any]:
    rijen = await _sql(
        "SELECT description, event_metadata FROM audit_logs WHERE event_type = :e AND tenant_id = :t",
        e=event_type,
        t=TENANT,
    )
    return list(rijen.all())


async def _post(
    integration_app: Any,
    pad: str,
    body: dict[str, Any],
    *,
    bon: bool = False,
    user_id: int = INITIATOR,
) -> Any:
    """Een POST als een gebruiker van tenant 1 (standaard 1: rol goedkeurder en admin), met CSRF en gebruiker vervangen."""
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.bonnen.dependencies import get_bon_dienst
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import db_manager, get_db

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(
        id=user_id, email=f"u{user_id}@integration.test", tenant_id=TENANT, roles=["admin"]
    )
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.api.v1.payables.dependencies import get_current_user as payables_gebruiker

    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        payables_gebruiker: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
    if bon and _AKTIEF:
        overrides[get_bon_dienst] = _AKTIEF[0].dienst
    token = _build_test_token(
        user_id=user_id, email=f"u{user_id}@integration.test", tenant_id=TENANT
    )
    integration_app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.post(pad, json=body)
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


async def _hitl(integration_app: Any, soort: str, body: dict[str, str]) -> Any:
    return await _post(integration_app, f"/api/v1/tools/hitl/{soort}", body)


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetSchoneGeval:
    async def test_a_read_upload_of_a_known_supplier_becomes_a_payable_without_a_human_click(
        self, worker: _NepWorker
    ) -> None:
        leverancier = await _leverancier()
        bestand_id = _upload(worker)

        uitkomst = await _verwerk(bestand_id)

        assert uitkomst["uitkomst"] == "vastgelegd", uitkomst
        assert await _facturen() == [("INK-2026-0042", "ontvangen", leverancier)]
        assert await _tickets() == []

    async def test_the_payable_is_logged_as_made_by_the_agent(self, worker: _NepWorker) -> None:
        await _leverancier()
        eerder = len(await _audit("payable_created"))

        await _verwerk(_upload(worker))

        nieuw = (await _audit("payable_created"))[eerder:]
        assert [r[1].get("via") for r in nieuw] == ["agent"]

    async def test_an_upload_is_processed_only_once(self, worker: _NepWorker) -> None:
        await _leverancier()
        bestand_id = _upload(worker)
        await _verwerk(bestand_id)

        tweede = await _verwerk(bestand_id)

        assert tweede["uitkomst"] == "al_verwerkt"
        assert len(await _facturen()) == 1

    async def test_an_upload_that_is_not_read_yet_is_left_alone(self, worker: _NepWorker) -> None:
        await _leverancier()
        worker.klaar = False
        bestand_id = _upload(worker)

        wachtend = await _verwerk(bestand_id)
        worker.klaar = True
        daarna = await _verwerk(bestand_id)

        assert (wachtend["uitkomst"], daarna["uitkomst"]) == ("nog_niet_klaar", "vastgelegd")

    async def test_without_a_responsible_person_nothing_happens(self, worker: _NepWorker) -> None:
        await _leverancier()
        bestand_id = _upload(worker)

        uitkomst = await _verwerk(bestand_id, door=None)

        assert uitkomst["uitkomst"] == "geweigerd"
        assert await _facturen() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestUitzonderingenGaanLangsEenMens:
    async def test_a_deviating_iban_gives_a_ticket_with_a_warning_and_no_payable(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier(iban=_ANDER_IBAN)
        bestand_id = _upload(worker)

        uitkomst = await _verwerk(bestand_id)

        assert uitkomst["uitkomst"] == "ticket", uitkomst
        assert await _facturen() == []
        assert [r[1] for r in await _leveranciers()] == [_ANDER_IBAN]
        payload = await _ticket_payload(uitkomst["ticket_ref"])
        assert "wijkt af" in payload["waarom"] and "fraude" in payload["waarom"]

    async def test_the_ticket_shows_the_source_and_what_the_agent_read(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier(iban=_ANDER_IBAN)
        bestand_id = _upload(worker)

        ref = (await _verwerk(bestand_id))["ticket_ref"]

        payload = await _ticket_payload(ref)
        assert (payload["bestand_id"], payload["invoice_number"], payload["amount_cents"]) == (
            bestand_id,
            "INK-2026-0042",
            121000,
        )
        assert (payload["iban"], payload["bekend_iban"]) == ("NL91ABNA******4300", "NL02ABNA******6789")

    async def test_an_unknown_supplier_gives_a_ticket_and_after_approval_both_exist(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        uitkomst = await _verwerk(_upload(worker))
        assert uitkomst["uitkomst"] == "ticket", uitkomst
        assert (await _facturen(), await _leveranciers()) == ([], [])

        antwoord = await _hitl(integration_app, "approve", {"ticket_ref": uitkomst["ticket_ref"]})

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["executed"] is True, antwoord.json()
        assert await _leveranciers() == [("Drukkerij Van Dijk BV", _IBAN)]
        assert [(f[0], f[1]) for f in await _facturen()] == [("INK-2026-0042", "ontvangen")]

    async def test_approving_a_deviating_iban_creates_the_payable_and_sets_the_new_iban(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _leverancier(iban=_ANDER_IBAN)
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        antwoord = await _hitl(integration_app, "approve", {"ticket_ref": ref})

        assert antwoord.json()["executed"] is True, antwoord.json()
        assert [r[1] for r in await _leveranciers()] == [_IBAN]
        assert len(await _facturen()) == 1

    async def test_rejecting_without_a_reason_is_refused(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        antwoord = await _hitl(integration_app, "reject", {"ticket_ref": ref, "reason": ""})

        assert antwoord.status_code == 422
        assert await _facturen() == []

    async def test_rejecting_with_a_reason_leaves_no_payable_and_no_supplier(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        antwoord = await _hitl(
            integration_app, "reject", {"ticket_ref": ref, "reason": "geen bestelling gevonden"}
        )

        assert antwoord.status_code == 200, antwoord.text
        assert (await _facturen(), await _leveranciers()) == ([], [])

    async def test_a_missing_field_gives_a_ticket_that_cannot_be_approved_into_a_payable(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _leverancier()
        worker.velden["vervaldatum"] = None
        uitkomst = await _verwerk(_upload(worker))
        assert uitkomst["uitkomst"] == "ticket", uitkomst

        antwoord = await _hitl(integration_app, "approve", {"ticket_ref": uitkomst["ticket_ref"]})

        assert antwoord.json()["executed"] is False
        assert await _facturen() == []

    async def test_the_ticket_names_the_missing_field(self, worker: _NepWorker) -> None:
        await _leverancier()
        worker.velden["vervaldatum"] = None

        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        assert "vervaldatum" in (await _ticket_payload(ref))["waarom"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenDubbeleFactuur:
    async def test_a_duplicate_gives_no_second_payable_and_no_ticket_but_a_dutch_reason(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier()
        await _verwerk(_upload(worker))

        tweede = await _verwerk(_upload(worker))

        assert tweede["uitkomst"] == "dubbel"
        assert tweede["reden"] == "Deze factuur van deze leverancier is al vastgelegd."
        assert len(await _facturen()) == 1
        assert await _tickets() == []

    async def test_the_reason_is_in_the_log(self, worker: _NepWorker) -> None:
        await _leverancier()
        await _verwerk(_upload(worker))
        eerder = len(await _audit("payable_duplicate_refused"))

        await _verwerk(_upload(worker))

        nieuw = (await _audit("payable_duplicate_refused"))[eerder:]
        assert [r[0] for r in nieuw] == ["Deze factuur van deze leverancier is al vastgelegd."]


@pytest.mark.integration
@pytest.mark.asyncio
class TestIsolatie:
    async def test_another_tenant_sees_neither_the_ticket_nor_the_payable(
        self, worker: _NepWorker
    ) -> None:
        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import PayableRepository
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        await _leverancier()
        assert (await _verwerk(_upload(worker)))["uitkomst"] == "vastgelegd"
        worker.velden["factuurnummer"] = "INK-2026-0099"
        worker.velden["iban"] = _ANDER_IBAN
        ticket = (await _verwerk(_upload(worker)))["ticket_ref"]

        async with db_manager.get_session() as session:
            facturen = await PayableRepository(session).list_for_tenant(ANDERE_TENANT)
            gevonden = await HITLTicketRepository(session).get(ticket, ANDERE_TENANT)

        assert (facturen, gevonden) == ([], None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanpassenViaDeBevestigroute:
    _BODY: dict[str, Any] = {
        "nieuwe_leverancier": {"name": "Drukkerij Van Dijk BV", "iban": _IBAN},
        "invoice_number": "INK-2026-0042",
        "amount_cents": 99900,
        "currency": "EUR",
        "invoice_date": "2026-10-01",
        "due_date": "2026-10-31",
    }

    async def test_adjusting_creates_the_payable_and_closes_the_ticket_with_the_reason(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
            {
                **self._BODY,
                "ticket_ref": ref,
                "reden": "bedrag aangepast na belletje met leverancier",
            },
            bon=True,
        )

        assert antwoord.status_code == 201, antwoord.text
        rijen = await _sql(
            "SELECT status, resolution_note FROM hitl_tickets WHERE ticket_ref = :r", r=ref
        )
        status, notitie = rijen.one()
        assert (status, "handmatig vastgelegd" in notitie, "belletje" in notitie) == (
            "rejected",
            True,
            True,
        )
        assert [f[0] for f in await _facturen()] == ["INK-2026-0042"]

    async def test_adjusting_without_a_reason_is_refused(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
            {**self._BODY, "ticket_ref": ref, "reden": ""},
            bon=True,
        )

        assert antwoord.status_code == 422
        assert await _facturen() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeToolsWeigerenWatNietKlopt:
    """De tools beoordelen zelf opnieuw: de agent (of een aanroeper) kan er geen uitzondering stil mee vastleggen."""

    async def test_the_medium_tool_refuses_an_exception_even_when_called_directly(
        self, worker: _NepWorker
    ) -> None:
        from src.core.tool_broker.payables_registry import PayablesToolRegistry

        await _leverancier(iban=_ANDER_IBAN)
        bestand_id = _upload(worker)

        antwoord = await PayablesToolRegistry().execute_payables_tool(
            "record_supplier_invoice", {"bestand_id": bestand_id}, tenant_id=TENANT
        )

        assert antwoord["success"] is False
        assert await _facturen() == []

    async def test_approving_after_the_supplier_changed_records_nothing(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]
        await _leverancier()

        antwoord = await _hitl(integration_app, "approve", {"ticket_ref": ref})

        assert antwoord.json()["executed"] is False
        assert await _facturen() == []

    async def test_a_name_with_an_invisible_control_character_is_not_trusted(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier()
        worker.velden["leverancier"] = "Drukkerij\u200bVan Dijk BV"

        uitkomst = await _verwerk(_upload(worker))

        assert uitkomst["uitkomst"] == "ticket"
        assert await _facturen() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanpassenGrenzen:
    _BODY: dict[str, Any] = {
        "nieuwe_leverancier": {"name": "Drukkerij Van Dijk BV", "iban": _IBAN},
        "invoice_number": "INK-2026-0042",
        "amount_cents": 121000,
        "currency": "EUR",
        "invoice_date": "2026-10-01",
        "due_date": "2026-10-31",
        "reden": "gecontroleerd met de leverancier gebeld",
    }

    async def test_an_unknown_ticket_gives_404_and_records_nothing(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        bestand_id = _upload(worker)
        await _verwerk(bestand_id)

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
            {**self._BODY, "ticket_ref": "hitl_00000000deadbeef"},
            bon=True,
        )

        assert antwoord.status_code == 404
        assert await _facturen() == []

    async def test_a_ticket_that_is_already_closed_cannot_be_used_again(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]
        await _hitl(integration_app, "reject", {"ticket_ref": ref, "reason": "geen bestelling gevonden"})

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
            {**self._BODY, "ticket_ref": ref},
            bon=True,
        )

        assert antwoord.status_code == 409
        assert await _facturen() == []

    async def test_the_ticket_of_another_upload_cannot_be_used(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        eerste = _upload(worker)
        ref = (await _verwerk(eerste))["ticket_ref"]
        tweede = _upload(worker)

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{tweede}/bevestiging",
            {**self._BODY, "ticket_ref": ref},
            bon=True,
        )

        assert antwoord.status_code == 409
        assert await _facturen() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeNieuweRepositorymethodesBlijvenBinnenDeTenant:
    """Elke nieuwe repositorymethode vraagt een isolatietest: tenant A ziet data van tenant B NIET."""

    async def _leverancier_van_tenant_2(self, naam: str, iban: str | None) -> int:
        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import NewSupplier, SupplierRepository

        async with db_manager.get_session() as session:
            rij = await SupplierRepository(session).add(
                ANDERE_TENANT, NewSupplier(name=naam, iban=iban)
            )
            await session.commit()
            return int(rij.id)

    async def test_find_match_does_not_match_a_supplier_of_another_tenant_on_name_or_iban(self) -> None:
        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import SupplierRepository

        await self._leverancier_van_tenant_2("Drukkerij Van Dijk BV", _IBAN)

        async with db_manager.get_session() as session:
            repo = SupplierRepository(session)
            op_naam = await repo.find_match(TENANT, naam="Drukkerij Van Dijk BV", iban=None)
            op_iban = await repo.find_match(TENANT, naam=None, iban=_IBAN)

        assert (op_naam, op_iban) == (None, None)

    async def test_find_duplicate_does_not_see_a_payable_of_another_tenant(self) -> None:
        from datetime import date

        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import NewPayable, PayableRepository

        leverancier = await self._leverancier_van_tenant_2("Leverancier twee", _IBAN)
        async with db_manager.get_session() as session:
            await PayableRepository(session).add(
                ANDERE_TENANT,
                NewPayable(
                    supplier_id=leverancier,
                    invoice_number="INK-2026-0042",
                    amount_cents=100,
                    invoice_date=date(2026, 10, 1),
                    due_date=date(2026, 10, 31),
                ),
                created_by=None,
            )
            await session.commit()

        async with db_manager.get_session() as session:
            gevonden = await PayableRepository(session).find_duplicate(
                TENANT, leverancier, "INK-2026-0042"
            )

        assert gevonden is None

    async def test_update_iban_does_not_touch_a_supplier_of_another_tenant(self) -> None:
        from src.core.database.database import db_manager
        from src.core.repositories.payable_repository import SupplierRepository

        leverancier = await self._leverancier_van_tenant_2("Leverancier twee", _ANDER_IBAN)

        async with db_manager.get_session() as session:
            bijgewerkt = await SupplierRepository(session).update_iban(TENANT, leverancier, _IBAN)
            await session.commit()

        assert bijgewerkt is None
        assert (await _sql("SELECT iban FROM suppliers WHERE id = :i", i=leverancier)).scalar() == _ANDER_IBAN


async def _zet_vier_ogen(aan: bool) -> None:
    waarde = '{"four_eyes_actions": ["propose_supplier_invoice"]}' if aan else "{}"
    await _sql("UPDATE tenants SET settings = CAST(:s AS JSON) WHERE id = :t", s=waarde, t=TENANT)


@pytest.mark.integration
@pytest.mark.asyncio
class TestGate2Reparaties:
    """Wat de twee reviewers van Gate 2 vonden en de bouwer naproefde."""

    async def test_a_receipt_is_never_picked_up_as_an_invoice(self, worker: _NepWorker) -> None:
        await _leverancier()
        bon = worker.dienst().uploaden(TENANT, "bon.pdf", _PDF)

        uitkomst = await _verwerk(bon)

        assert uitkomst["uitkomst"] == "onbekend"
        assert await _facturen() == []

    async def test_the_ticket_says_by_itself_that_the_iban_deviates(self, worker: _NepWorker) -> None:
        await _leverancier(iban=_ANDER_IBAN)

        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        assert (await _ticket_payload(ref))["iban_wijkt_af"] is True

    async def test_the_ticket_says_it_cannot_be_approved_when_a_field_is_missing(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier()
        worker.velden["vervaldatum"] = None

        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        assert (await _ticket_payload(ref))["goedkeuren_mogelijk"] is False

    async def test_the_ticket_of_an_unknown_supplier_can_be_approved(self, worker: _NepWorker) -> None:
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        assert (await _ticket_payload(ref))["goedkeuren_mogelijk"] is True

    async def test_an_unknown_supplier_without_an_iban_on_the_invoice_still_gets_a_ticket(
        self, worker: _NepWorker
    ) -> None:
        worker.velden["iban"] = None

        uitkomst = await _verwerk(_upload(worker))

        assert uitkomst["uitkomst"] == "ticket"
        assert await _facturen() == []

    async def test_a_name_that_differs_from_the_supplier_with_that_iban_gives_a_ticket(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier(naam="Totaal Andere Naam BV", iban=_IBAN)

        uitkomst = await _verwerk(_upload(worker))

        assert uitkomst["uitkomst"] == "ticket"
        assert "anders dan" in str((await _ticket_payload(uitkomst["ticket_ref"]))["waarom"])

    async def test_a_name_that_looks_like_a_known_supplier_is_pointed_out(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier(naam="Drukkerij Van Dijk B.V.", iban=_ANDER_IBAN)

        uitkomst = await _verwerk(_upload(worker))

        assert uitkomst["uitkomst"] == "ticket"
        assert "lijkt op" in str((await _ticket_payload(uitkomst["ticket_ref"]))["waarom"])

    async def test_a_step_that_fails_after_the_claim_leaves_a_failure_and_no_stuck_claim(
        self, worker: _NepWorker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.als.agents.skills.crediteuren import CrediteurenSkill

        await _leverancier()
        bestand_id = _upload(worker)

        async def _stuk(self: Any, besluit: str) -> Any:
            raise RuntimeError("broker weg")

        monkeypatch.setattr(CrediteurenSkill, "act", _stuk)
        eerste = await _verwerk(bestand_id)
        stand = _koppeling(worker).lees(TENANT, bestand_id)

        assert (eerste["uitkomst"], (stand or {}).get("uitkomst")) == ("niet_gelukt", "mislukt")

    async def test_a_claim_that_is_stuck_on_busy_is_taken_over_after_ten_minutes(
        self, worker: _NepWorker
    ) -> None:
        await _leverancier()
        bestand_id = _upload(worker)
        koppeling = _koppeling(worker)
        koppeling.claim(TENANT, bestand_id, INITIATOR)
        koppeling.schrijf(
            TENANT,
            bestand_id,
            {"payable_id": None, "uitkomst": "bezig", "door": INITIATOR, "aangemaakt": "2020-01-01T00:00:00+00:00"},
        )

        uitkomst = await _verwerk(bestand_id)

        assert uitkomst["uitkomst"] == "vastgelegd"

    async def test_a_fresh_claim_on_busy_is_left_alone(self, worker: _NepWorker) -> None:
        await _leverancier()
        bestand_id = _upload(worker)
        _koppeling(worker).claim(TENANT, bestand_id, INITIATOR)

        uitkomst = await _verwerk(bestand_id)

        assert uitkomst["uitkomst"] == "al_verwerkt"
        assert await _facturen() == []

    async def test_the_payable_and_the_log_name_the_user_who_uploaded(self, worker: _NepWorker) -> None:
        await _leverancier()
        eerder = len(await _audit("payable_created"))

        await _verwerk(_upload(worker))

        rij = (await _sql("SELECT created_by_user_id FROM payables WHERE tenant_id = :t", t=TENANT)).one()
        nieuw = (await _audit("payable_created"))[eerder:]
        assert (rij[0], [r[1].get("initiated_by") for r in nieuw]) == (INITIATOR, [INITIATOR])

    async def test_changing_an_iban_after_approval_is_traceable_without_the_numbers(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _leverancier(iban=_ANDER_IBAN)
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]
        eerder = len(await _audit("supplier_iban_changed"))

        await _hitl(integration_app, "approve", {"ticket_ref": ref})

        details = (await _audit("supplier_iban_changed"))[eerder:][0][1]
        assert (details["ticket_ref"], details["oud"], details["nieuw"]) == (
            ref,
            "NL02ABNA******6789",
            "NL91ABNA******4300",
        )
        assert _IBAN not in str(details) and _ANDER_IBAN not in str(details)


@pytest.mark.integration
@pytest.mark.asyncio
class TestBronEnBesluitInDeStand:
    async def test_the_ticket_names_the_file_the_user_uploaded(self, worker: _NepWorker) -> None:
        ref = (await _verwerk(_upload(worker)))["ticket_ref"]

        waarom = str((await _ticket_payload(ref))["waarom"])

        assert "'factuur.pdf'" in waarom

    async def test_the_status_says_that_the_approver_rejected_the_ticket(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        from src.core.database.database import db_manager
        from src.core.services.inkoopfactuur_inlezen import InkoopfactuurInlezen

        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]
        await _hitl(integration_app, "reject", {"ticket_ref": ref, "reason": "geen opdracht gegeven"})

        async with db_manager.get_session() as session:
            stand = await InkoopfactuurInlezen(
                session, worker.dienst()
            ).voorstel(TENANT, bestand_id)

        assert stand["verwerking"]["uitkomst"] == "afgewezen"  # type: ignore[index]

    async def test_the_status_of_an_open_ticket_stays_a_ticket(self, worker: _NepWorker) -> None:
        from src.core.database.database import db_manager
        from src.core.services.inkoopfactuur_inlezen import InkoopfactuurInlezen

        bestand_id = _upload(worker)
        await _verwerk(bestand_id)

        async with db_manager.get_session() as session:
            stand = await InkoopfactuurInlezen(
                session, worker.dienst()
            ).voorstel(TENANT, bestand_id)

        assert stand["verwerking"]["uitkomst"] == "ticket"  # type: ignore[index]


def _koppeling(worker: _NepWorker) -> Any:
    from src.core.als.bonlezer.factuur import FactuurKoppeling

    return FactuurKoppeling(worker.root)


@pytest.mark.integration
@pytest.mark.asyncio
class TestHerstelNaEenVerbruiktTicket:
    async def test_a_second_invoice_of_the_same_new_supplier_recovers_after_the_first_is_approved(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        eerste = _upload(worker)
        ref_een = (await _verwerk(eerste))["ticket_ref"]
        worker.velden["factuurnummer"] = "INK-2026-0099"
        tweede = _upload(worker)
        ref_twee = (await _verwerk(tweede))["ticket_ref"]
        await _hitl(integration_app, "approve", {"ticket_ref": ref_een})

        antwoord = await _hitl(integration_app, "approve", {"ticket_ref": ref_twee})
        opnieuw = await _verwerk(tweede)

        assert antwoord.json()["executed"] is False
        assert opnieuw["uitkomst"] == "vastgelegd"
        assert sorted(f[0] for f in await _facturen()) == ["INK-2026-0042", "INK-2026-0099"]

    async def test_a_ticket_that_cannot_work_because_of_a_missing_field_keeps_its_claim(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _leverancier()
        worker.velden["vervaldatum"] = None
        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]

        await _hitl(integration_app, "approve", {"ticket_ref": ref})
        opnieuw = await _verwerk(bestand_id)

        assert opnieuw["uitkomst"] == "al_verwerkt"
        assert len(await _tickets()) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanpassenEnVierOgen:
    _BODY: dict[str, Any] = {
        "nieuwe_leverancier": {"name": "Drukkerij Van Dijk BV", "iban": _IBAN},
        "invoice_number": "INK-2026-0042",
        "amount_cents": 121000,
        "currency": "EUR",
        "invoice_date": "2026-10-01",
        "due_date": "2026-10-31",
        "reden": "gecontroleerd met de leverancier gebeld",
    }

    async def test_the_uploader_cannot_close_his_own_ticket_when_four_eyes_is_on(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _zet_vier_ogen(True)
        try:
            bestand_id = _upload(worker)
            ref = (await _verwerk(bestand_id))["ticket_ref"]

            antwoord = await _post(
                integration_app,
                f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
                {**self._BODY, "ticket_ref": ref},
                bon=True,
            )
        finally:
            await _zet_vier_ogen(False)

        assert antwoord.status_code == 403
        assert await _facturen() == []

    async def test_a_colleague_can_close_the_ticket_when_four_eyes_is_on(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        await _zet_vier_ogen(True)
        try:
            bestand_id = _upload(worker)
            ref = (await _verwerk(bestand_id))["ticket_ref"]

            antwoord = await _post(
                integration_app,
                f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
                {**self._BODY, "ticket_ref": ref},
                bon=True,
                user_id=101,
            )
        finally:
            await _zet_vier_ogen(False)

        assert antwoord.status_code == 201, antwoord.text
        assert len(await _facturen()) == 1

    async def test_the_uploader_can_close_his_own_ticket_when_four_eyes_is_off(
        self, worker: _NepWorker, integration_app: Any
    ) -> None:
        bestand_id = _upload(worker)
        ref = (await _verwerk(bestand_id))["ticket_ref"]

        antwoord = await _post(
            integration_app,
            f"/api/v1/payables/inlezen/{bestand_id}/bevestiging",
            {**self._BODY, "ticket_ref": ref},
            bon=True,
        )

        assert antwoord.status_code == 201, antwoord.text
