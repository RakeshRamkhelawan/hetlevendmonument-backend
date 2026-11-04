"""Crediteuren dag 2 via de API: een inkoopfactuur uploaden, de stand zien en aanpassen (Keten F, agent-first).

Echte app-stack (`register_all_routers`), echte Postgres, de echte `require_resource_permission`. Alleen CSRF is vervangen, de
bonlezer (`BonDienst` met een tijdelijke uploadmap en een nepwerker die precies meldt wat de echte zou melden, inclusief de sha256 van
de bytes) en de START van de crediteurenagent: die wordt hier opgevangen en geteld, zodat deze tests de API meten en niet de agent.
De agent zelf staat in `test_crediteurenagent_verwerkt_factuur.py`.

Sinds de agent-first-brief is er geen normale route meer waarbij een medewerker elk voorstel bevestigt. Wat hier staat:

- uploaden start de agent (precies een keer, met de tenant en de gebruiker van de upload);
- de stand toont de gelezen velden, het voorstel voor de leverancier (met een waarschuwing bij een afwijkend IBAN) en wat de agent deed;
- een gelezen factuur zonder stand start de agent alsnog (een herstart van de API mag niets laten liggen);
- aanpassen (de enige bevestiging) vraagt een ticket, een reden en het goedkeurrecht voor crediteuren.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/v1/payables"
INLEZEN = f"{URL}/inlezen"
LEVERANCIERS = f"{URL}/suppliers"

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

_AANPASSING: dict[str, Any] = {
    "nieuwe_leverancier": {"name": "Drukkerij Van Dijk BV", "iban": _IBAN},
    "invoice_number": "INK-2026-0042",
    "amount_cents": 121000,
    "currency": "EUR",
    "invoice_date": "2026-10-01",
    "due_date": "2026-10-31",
    "ticket_ref": "hitl_0123456789abcdef",
    "reden": "bedrag aangepast na telefoontje met de leverancier",
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


@pytest.fixture
def worker(tmp_path: Path) -> _NepWorker:
    return _NepWorker(tmp_path)


@pytest.fixture
def gestart() -> list[tuple[int, str, int]]:
    """De starts van de crediteurenagent die de API deed (tenant, bestand, gebruiker)."""
    return []


@pytest_asyncio.fixture
async def api(
    integration_app: Any,
    postgres_session: AsyncSession,
    worker: _NepWorker,
    gestart: list[tuple[int, str, int]],
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.als.bonlezer.upload import BonDienst
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.api.v1.bonnen.dependencies import get_bon_dienst
    from src.core.api.v1.payables.inlezen_dependencies import get_verwerking_starter
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def _geen_csrf() -> None:
        return None

    def _dienst() -> BonDienst:
        return BonDienst(worker.root, verstuur=worker.verstuur, haal=worker.haal)

    def _starter() -> Any:
        return lambda tenant_id, bestand_id, user_id: gestart.append(
            (tenant_id, bestand_id, user_id)
        )

    overrides = {
        get_db: _db,
        api_get_db: _db,
        validate_csrf_token: _geen_csrf,
        get_bon_dienst: _dienst,
        get_verwerking_starter: _starter,
    }
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


async def _upload(api: AsyncClient, inhoud: bytes = _PDF, naam: str = "factuur.pdf") -> str:
    antwoord = await api.post(INLEZEN, files={"file": (naam, inhoud, "application/pdf")})
    assert antwoord.status_code == 201, antwoord.text
    return str(antwoord.json()["data"]["bestand_id"])


async def _leverancier(api: AsyncClient, naam: str, iban: str | None = None) -> int:
    antwoord = await api.post(LEVERANCIERS, json={"name": naam, "iban": iban})
    assert antwoord.status_code == 201, antwoord.text
    return int(antwoord.json()["data"]["id"])


async def _voorstel(api: AsyncClient, bestand_id: str) -> dict[str, Any]:
    return dict((await api.get(f"{INLEZEN}/{bestand_id}")).json()["data"]["voorstel"])


@pytest.mark.integration
@pytest.mark.asyncio
class TestUploadenStartDeAgent:
    async def test_an_upload_starts_the_agent_once_with_the_tenant_and_user_of_the_upload(
        self, api: AsyncClient, gestart: list[tuple[int, str, int]]
    ) -> None:
        bestand_id = await _upload(api)

        assert gestart == [(1, bestand_id, 1)]

    async def test_an_upload_alone_creates_no_payable(self, api: AsyncClient) -> None:
        await _upload(api)

        assert (await api.get(URL)).json()["data"] == []

    async def test_a_wrong_file_type_is_refused_in_dutch_and_starts_nothing(
        self, api: AsyncClient, gestart: list[tuple[int, str, int]]
    ) -> None:
        antwoord = await api.post(
            INLEZEN, files={"file": ("x.exe", b"MZ", "application/octet-stream")}
        )

        assert antwoord.status_code == 415
        assert "pdf" in antwoord.json()["error"]["message"]
        assert gestart == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeStand:
    async def test_the_status_shows_the_read_fields(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)

        data = (await api.get(f"{INLEZEN}/{bestand_id}")).json()["data"]

        assert (data["status"], data["velden"]["factuurnummer"], data["velden"]["iban"]) == (
            "gelezen",
            "INK-2026-0042",
            _IBAN,
        )

    async def test_the_proposal_has_no_supplier_when_none_is_known(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)

        voorstel = await _voorstel(api, bestand_id)

        assert (voorstel["leverancier_id"], voorstel["iban_wijkt_af"]) == (None, False)

    async def test_a_known_supplier_is_proposed_on_name(self, api: AsyncClient) -> None:
        leverancier = await _leverancier(api, "drukkerij van dijk bv")
        bestand_id = await _upload(api)

        voorstel = await _voorstel(api, bestand_id)

        assert (voorstel["leverancier_id"], voorstel["gevonden_op"]) == (leverancier, "naam")

    async def test_a_known_supplier_is_proposed_on_iban_when_the_name_differs(
        self, api: AsyncClient, worker: _NepWorker
    ) -> None:
        leverancier = await _leverancier(api, "Van Dijk Drukwerk", _IBAN)
        worker.velden["leverancier"] = "Iets heel anders"
        bestand_id = await _upload(api)

        voorstel = await _voorstel(api, bestand_id)

        assert (voorstel["leverancier_id"], voorstel["gevonden_op"]) == (leverancier, "iban")

    async def test_a_deviating_iban_gives_a_warning_in_the_proposal(
        self, api: AsyncClient, worker: _NepWorker
    ) -> None:
        await _leverancier(api, "Drukkerij Van Dijk BV", _IBAN)
        worker.velden["iban"] = _ANDER_IBAN
        bestand_id = await _upload(api)

        assert (await _voorstel(api, bestand_id))["iban_wijkt_af"] is True

    async def test_the_same_iban_gives_no_warning(self, api: AsyncClient) -> None:
        await _leverancier(api, "Drukkerij Van Dijk BV", _IBAN)
        bestand_id = await _upload(api)

        assert (await _voorstel(api, bestand_id))["iban_wijkt_af"] is False

    async def test_a_receipt_of_the_receipts_page_does_not_exist_as_an_invoice(
        self, api: AsyncClient, worker: _NepWorker
    ) -> None:
        from src.core.als.bonlezer.upload import BonDienst

        dienst = BonDienst(worker.root, verstuur=worker.verstuur, haal=worker.haal)
        bon = dienst.uploaden(1, "bon.pdf", _PDF)

        assert (await api.get(f"{INLEZEN}/{bon}")).status_code == 404

    async def test_an_upload_of_another_tenant_does_not_exist_here(
        self, api: AsyncClient, worker: _NepWorker
    ) -> None:
        from src.core.als.bonlezer.upload import BonDienst

        dienst = BonDienst(worker.root, verstuur=worker.verstuur, haal=worker.haal)
        vreemd = dienst.uploaden(2, "factuur.pdf", _PDF, "factuur")

        assert (await api.get(f"{INLEZEN}/{vreemd}")).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenGelezenFactuurZonderStandStartDeAgentAlsnog:
    async def test_reading_the_status_of_a_read_upload_without_a_state_starts_the_agent(
        self, api: AsyncClient, gestart: list[tuple[int, str, int]]
    ) -> None:
        bestand_id = await _upload(api)
        gestart.clear()

        await api.get(f"{INLEZEN}/{bestand_id}")

        assert gestart == [(1, bestand_id, 1)]

    async def test_an_upload_that_is_not_read_yet_does_not_start_the_agent(
        self, api: AsyncClient, worker: _NepWorker, gestart: list[tuple[int, str, int]]
    ) -> None:
        worker.klaar = False
        bestand_id = await _upload(api)
        gestart.clear()

        await api.get(f"{INLEZEN}/{bestand_id}")

        assert gestart == []

    async def test_an_upload_the_agent_already_handled_is_not_started_again(
        self, api: AsyncClient, worker: _NepWorker, gestart: list[tuple[int, str, int]]
    ) -> None:
        from src.core.als.bonlezer.factuur import FactuurKoppeling

        bestand_id = await _upload(api)
        koppeling = FactuurKoppeling(worker.root)
        koppeling.claim(1, bestand_id)
        koppeling.schrijf(
            1, bestand_id, {"payable_id": None, "uitkomst": "ticket", "ticket_ref": "hitl_ab"}
        )
        gestart.clear()

        data = (await api.get(f"{INLEZEN}/{bestand_id}")).json()["data"]

        assert (gestart, data["verwerking"]["uitkomst"]) == ([], "ticket")


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanpassenIsDeEnigeBevestiging:
    async def _pas_aan(self, api: AsyncClient, bestand_id: str, **wijzig: Any) -> Any:
        return await api.post(f"{INLEZEN}/{bestand_id}/bevestiging", json={**_AANPASSING, **wijzig})

    async def test_a_confirmation_without_a_ticket_is_refused(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)
        zonder = {k: v for k, v in _AANPASSING.items() if k not in ("ticket_ref", "reden")}

        antwoord = await api.post(f"{INLEZEN}/{bestand_id}/bevestiging", json=zonder)

        assert antwoord.status_code == 422
        assert (await api.get(URL)).json()["data"] == []

    async def test_a_reason_without_a_ticket_is_refused(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)
        zonder = {k: v for k, v in _AANPASSING.items() if k != "ticket_ref"}

        antwoord = await api.post(f"{INLEZEN}/{bestand_id}/bevestiging", json=zonder)

        assert antwoord.status_code == 422

    async def test_a_reason_that_is_too_short_is_refused(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)

        antwoord = await self._pas_aan(api, bestand_id, reden="te kort")

        assert antwoord.status_code == 422

    async def test_an_administrator_without_the_approval_right_cannot_adjust(
        self, api: AsyncClient
    ) -> None:
        bestand_id = await _upload(api)

        antwoord = await self._pas_aan(api, bestand_id)

        assert antwoord.status_code == 403
        assert (await api.get(URL)).json()["data"] == []

    async def test_a_tenant_id_in_the_body_is_refused(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)

        antwoord = await self._pas_aan(api, bestand_id, tenant_id=2)

        assert antwoord.status_code == 422

    async def test_exactly_one_of_supplier_and_new_supplier_is_required(
        self, api: AsyncClient
    ) -> None:
        bestand_id = await _upload(api)

        geen = await self._pas_aan(api, bestand_id, nieuwe_leverancier=None)
        beide = await self._pas_aan(api, bestand_id, supplier_id=1)

        assert (geen.status_code, beide.status_code) == (422, 422)

    async def test_a_fraction_of_a_euro_is_refused_as_amount(self, api: AsyncClient) -> None:
        bestand_id = await _upload(api)

        antwoord = await self._pas_aan(api, bestand_id, amount_cents=1210.5)

        assert antwoord.status_code == 422
