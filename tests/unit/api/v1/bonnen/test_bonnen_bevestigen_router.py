"""De routes voor lijst, bevestigen en export van bonnen (bonlezer dag 4).

`GET /api/v1/bonnen` (lijst), `PUT /api/v1/bonnen/{id}/bevestiging` (corrigeren en bevestigen),
`GET /api/v1/bonnen/bevestigd.csv` (export) en de uitbreiding van `GET /api/v1/bonnen/{id}` met wat er
gecontroleerd moet worden en wat al bevestigd is. De opslag en de regels zitten in `BonBevestiging`
(`tests/unit/bonlezer/test_bevestiging.py`); hier alleen de HTTP-laag: de tenant uit de ingelogde gebruiker,
de statuscodes, de auditregel en de vorm van het antwoord.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from dramatiq.results import ResultMissing
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.als.bonlezer.bevestiging import BonBevestiging
from src.core.als.bonlezer.upload import BonDienst
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.bonnen.dependencies import (
    _toets_read,
    _toets_write,
    get_bon_bevestiging,
    get_bon_dienst,
    get_current_user,
)
from src.core.api.v1.bonnen.router import router as bonnen_router
from src.core.auth.auth_service import UserResponse
from src.core.database.database import get_db
from src.core.exceptions.handlers import register_exception_handlers
from src.core.shared.rate_limiter import _rate_limiter

pytestmark = pytest.mark.unit

PDF = b"%PDF-1.4\n% een proefbestand\n"
GOED = {
    "leverancier": "Bakkerij De Korenaar B.V.",
    "datum": "2026-10-01",
    "totaal": "12.10",
    "factuurnummer": "F-2026-001",
    "btw": {"9": "0.50", "21": "1.60"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}


def _gebruiker(tenant_id: int) -> UserResponse:
    return UserResponse(
        id=10 + tenant_id, email="a@example.test", tenant_id=tenant_id, roles=["user"]
    )


class _Systeem:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.resultaten: dict[str, dict[str, object]] = {}
        self.verstuurd = 0
        self.dienst = BonDienst(root, verstuur=self._verstuur, haal=self._haal)
        self.bevestiging = BonBevestiging(root)

    def _verstuur(self, tenant_id: int, bestand_id: str) -> str:
        self.verstuurd += 1
        return f"bericht-{self.verstuurd}"

    def _haal(self, message_id: str) -> dict[str, object]:
        if message_id not in self.resultaten:
            raise ResultMissing(message_id)  # type: ignore[call-arg]
        return self.resultaten[message_id]

    def client(self, tenant_id: int, *, csrf_aan: bool = False) -> TestClient:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(bonnen_router)

        async def _mock_db() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        app.dependency_overrides[get_db] = _mock_db
        app.dependency_overrides[get_current_user] = lambda: _gebruiker(tenant_id)
        app.dependency_overrides[_toets_write] = lambda: 1
        app.dependency_overrides[_toets_read] = lambda: 1
        if csrf_aan is False:
            app.dependency_overrides[validate_csrf_token] = lambda: None
        app.dependency_overrides[get_bon_dienst] = lambda: self.dienst
        app.dependency_overrides[get_bon_bevestiging] = lambda: self.bevestiging
        return TestClient(app)

    def bon(self, tenant_id: int = 1) -> str:
        return self.dienst.uploaden(tenant_id, "a.pdf", PDF)


@pytest.fixture(autouse=True)
def _leeg_de_snelheidsbegrenzing() -> Iterator[None]:
    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


@pytest.fixture
def s(tmp_path: Path) -> _Systeem:
    return _Systeem(tmp_path)


def _bevestig(client: TestClient, bestand_id: str, velden: object = GOED):  # type: ignore[no-untyped-def]
    return client.put(f"/api/v1/bonnen/{bestand_id}/bevestiging", json={"velden": velden})


class TestDeLijst:
    def test_the_list_shows_the_own_bonnen(self, s: _Systeem) -> None:
        bestand_id = s.bon(1)
        s.bon(2)

        data = s.client(1).get("/api/v1/bonnen").json()["data"]

        assert ([i["bestand_id"] for i in data["items"]], data["totaal"]) == ([bestand_id], 1)

    def test_the_answer_has_the_standard_shape(self, s: _Systeem) -> None:
        antwoord = s.client(1).get("/api/v1/bonnen").json()

        assert antwoord["success"] is True and set(antwoord["data"]) == {"items", "totaal"}

    def test_a_limit_above_the_maximum_is_refused(self, s: _Systeem) -> None:
        assert s.client(1).get("/api/v1/bonnen", params={"limit": 1001}).status_code == 422

    def test_a_negative_offset_is_refused(self, s: _Systeem) -> None:
        assert s.client(1).get("/api/v1/bonnen", params={"offset": -1}).status_code == 422

    def test_the_limit_is_applied(self, s: _Systeem) -> None:
        for _ in range(3):
            s.bon()

        items = s.client(1).get("/api/v1/bonnen", params={"limit": 2}).json()["data"]["items"]

        assert len(items) == 2

    def test_a_tenant_id_in_the_query_is_ignored(self, s: _Systeem) -> None:
        s.bon(2)

        data = s.client(1).get("/api/v1/bonnen", params={"tenant_id": 2}).json()["data"]

        assert data["totaal"] == 0


class TestBevestigen:
    def test_a_confirmation_gets_200(self, s: _Systeem) -> None:
        assert _bevestig(s.client(1), s.bon()).status_code == 200

    def test_the_answer_says_when_it_was_confirmed(self, s: _Systeem) -> None:
        data = _bevestig(s.client(1), s.bon()).json()["data"]

        assert set(data) == {"bestand_id", "bevestigd_op"}

    def test_the_corrected_fields_are_stored_for_the_tenant_of_the_user(self, s: _Systeem) -> None:
        bestand_id = s.bon(5)

        _bevestig(s.client(5), bestand_id, {**GOED, "totaal": "99.00"})

        assert s.bevestiging.bevestigd(5, bestand_id)["velden"]["totaal"] == "99.00"  # type: ignore[index]

    def test_a_wrong_vat_number_gets_422_and_names_the_field(self, s: _Systeem) -> None:
        antwoord = _bevestig(s.client(1), s.bon(), {**GOED, "btw_nummer": "NL123"})

        assert (antwoord.status_code, "btw_nummer" in antwoord.json()["error"]["message"]) == (
            422,
            True,
        )

    def test_a_wrong_chamber_number_gets_422(self, s: _Systeem) -> None:
        assert _bevestig(s.client(1), s.bon(), {**GOED, "kvk_nummer": "12"}).status_code == 422

    def test_nothing_is_stored_after_a_refusal(self, s: _Systeem) -> None:
        bestand_id = s.bon()

        _bevestig(s.client(1), bestand_id, {**GOED, "kvk_nummer": "12"})

        assert s.bevestiging.bevestigd(1, bestand_id) is None

    def test_another_tenant_gets_404(self, s: _Systeem) -> None:
        assert _bevestig(s.client(2), s.bon(1)).status_code == 404

    def test_an_unknown_bon_gets_404(self, s: _Systeem) -> None:
        assert _bevestig(s.client(1), "0" * 32 + ".pdf").status_code == 404

    def test_a_tenant_id_in_the_body_is_refused(self, s: _Systeem) -> None:
        antwoord = s.client(1).put(
            f"/api/v1/bonnen/{s.bon()}/bevestiging", json={"velden": GOED, "tenant_id": 2}
        )

        assert antwoord.status_code == 422

    def test_a_body_without_fields_is_refused(self, s: _Systeem) -> None:
        assert s.client(1).put(f"/api/v1/bonnen/{s.bon()}/bevestiging", json={}).status_code == 422

    def test_fields_that_are_not_a_dict_are_refused(self, s: _Systeem) -> None:
        assert _bevestig(s.client(1), s.bon(), ["totaal"]).status_code == 422


class TestDeAuditregel:
    @staticmethod
    def _met_audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        from src.core.api.v1.bonnen import dependencies as deps

        logger = AsyncMock()
        monkeypatch.setattr(deps.AuditService, "log_event", logger)
        return logger

    def test_a_confirmation_writes_an_audit_line(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logger = self._met_audit(monkeypatch)

        _bevestig(s.client(1), s.bon())

        assert logger.await_args.kwargs["event_type"] == "bon_bevestigd"

    def test_the_audit_line_has_who_and_the_tenant(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logger = self._met_audit(monkeypatch)

        _bevestig(s.client(7), s.bon(7))

        assert (logger.await_args.kwargs["user_id"], logger.await_args.kwargs["tenant_id"]) == (
            17,
            7,
        )

    def test_the_audit_line_has_no_field_values(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logger = self._met_audit(monkeypatch)

        _bevestig(s.client(1), s.bon())

        tekst = str(logger.await_args.kwargs)
        assert "Korenaar" not in tekst and "NL123456789B01" not in tekst and "12.10" not in tekst

    def test_a_refusal_writes_no_audit_line(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logger = self._met_audit(monkeypatch)

        _bevestig(s.client(1), s.bon(), {**GOED, "kvk_nummer": "1"})

        assert logger.await_count == 0


class TestDeStatusMetControleEnBevestiging:
    @staticmethod
    def _gelezen(s: _Systeem, velden: dict[str, object]) -> str:
        bestand_id = s.bon()
        s.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": velden,
        }
        return bestand_id

    def test_fields_that_do_not_check_out_are_marked_to_be_checked(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, {**GOED, "btw_nummer": "x"})

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert data["controleren"] == {"btw_nummer": "controleren"}

    def test_a_clean_read_has_nothing_to_check(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, dict(GOED))

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert data["controleren"] == {}

    def test_text_fields_are_cleaned_when_shown(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, {**GOED, "leverancier": "Bak\u202eker\x00ij"})

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert data["velden"]["leverancier"] == "Bakkerij"

    def test_html_is_shown_as_plain_text(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, {**GOED, "leverancier": "<script>alert(1)</script>"})

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert data["velden"]["leverancier"] == "<script>alert(1)</script>"

    def test_an_unconfirmed_bon_has_no_confirmation(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, dict(GOED))

        assert s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]["bevestigd"] is None

    def test_a_confirmed_bon_shows_the_confirmed_fields(self, s: _Systeem) -> None:
        bestand_id = self._gelezen(s, dict(GOED))
        _bevestig(s.client(1), bestand_id, {**GOED, "totaal": "99.00"})

        bevestigd = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]["bevestigd"]

        assert (bevestigd["velden"]["totaal"], "bevestigd_op" in bevestigd) == ("99.00", True)

    def test_the_confirmed_fields_are_still_shown_after_the_result_has_expired(
        self, s: _Systeem
    ) -> None:
        bestand_id = self._gelezen(s, dict(GOED))
        _bevestig(s.client(1), bestand_id)
        s.resultaten.clear()

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert (data["status"], data["bevestigd"]["velden"]["totaal"]) == ("verlopen", "12.10")

    def test_a_status_without_fields_has_no_check_list(self, s: _Systeem) -> None:
        bestand_id = s.bon()

        data = s.client(1).get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert (data["status"], "controleren" in data) == ("wachten", False)


class TestDeExport:
    def test_the_export_is_a_csv_download(self, s: _Systeem) -> None:
        antwoord = s.client(1).get("/api/v1/bonnen/bevestigd.csv")

        assert (
            antwoord.status_code,
            antwoord.headers["content-type"].startswith("text/csv"),
            "attachment" in antwoord.headers["content-disposition"],
        ) == (200, True, True)

    def test_the_export_contains_the_confirmed_bonnen_of_the_own_tenant(self, s: _Systeem) -> None:
        _bevestig(s.client(1), s.bon(1))
        _bevestig(s.client(2), s.bon(2))

        regels = s.client(1).get("/api/v1/bonnen/bevestigd.csv").text.strip().splitlines()

        assert len(regels) == 2

    def test_a_formula_in_a_field_is_neutralised(self, s: _Systeem) -> None:
        _bevestig(s.client(1), s.bon(), {**GOED, "leverancier": "=SUM(A1)"})

        assert "'=SUM(A1)" in s.client(1).get("/api/v1/bonnen/bevestigd.csv").text

    def test_the_export_is_not_taken_for_a_bon_id(self, s: _Systeem) -> None:
        """De vaste padnaam moet VOOR `/{bestand_id}` staan, anders is het een onbekende bon (404)."""
        assert s.client(1).get("/api/v1/bonnen/bevestigd.csv").status_code != 404


class TestCsrfEnLimieten:
    """Security-review dag 4: schrijven vraagt een CSRF-token, lezen en schrijven hebben een grens per gebruiker."""

    def test_a_confirmation_without_a_csrf_token_is_refused(self, s: _Systeem) -> None:
        bestand_id = s.bon()

        antwoord = _bevestig(s.client(1, csrf_aan=True), bestand_id)

        assert antwoord.status_code == 403

    def test_an_upload_without_a_csrf_token_is_refused(self, s: _Systeem) -> None:
        antwoord = s.client(1, csrf_aan=True).post(
            "/api/v1/bonnen", files={"file": ("a.pdf", PDF, "application/pdf")}
        )

        assert antwoord.status_code == 403

    def test_the_61st_read_in_a_minute_is_429(self, s: _Systeem) -> None:
        client = s.client(1)

        statussen = [client.get("/api/v1/bonnen").status_code for _ in range(61)]

        assert statussen[-1] == 429 and statussen[:60] == [200] * 60

    def test_the_31st_confirmation_in_a_minute_is_429(self, s: _Systeem) -> None:
        client = s.client(1)
        bestand_id = s.bon()

        statussen = [_bevestig(client, bestand_id).status_code for _ in range(31)]

        assert statussen[-1] == 429
