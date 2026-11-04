"""De HTTP-laag van de bon-upload (bonlezer dag 3): `POST /api/v1/bonnen` en `GET /api/v1/bonnen/{id}`.

De opslag en de controles zitten in `BonDienst` (`tests/unit/bonlezer/test_upload.py`); hier alleen wat
de route zelf moet doen: de tenant uit de ingelogde gebruiker halen (nooit uit het verzoek), de
foutcodes en de vorm van het antwoord. Verzending en resultaatopslag zijn nagemaakt.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator, Iterator
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from dramatiq.results import ResultMissing
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.als.bonlezer.upload import MAX_OPENSTAAND, BonDienst
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.bonnen.dependencies import (
    _toets_read,
    _toets_write,
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


def _gebruiker(tenant_id: int) -> UserResponse:
    return UserResponse(
        id=10 + tenant_id, email="a@example.test", tenant_id=tenant_id, roles=["user"]
    )


class _Systeem:
    """Een gedeelde uploadmap met een nagemaakte worker, en een client per tenant."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.verstuurd: list[tuple[int, str]] = []
        self.resultaten: dict[str, dict[str, object]] = {}
        self.verstuur_fout: Exception | None = None
        self.dienst = BonDienst(root, verstuur=self._verstuur, haal=self._haal)

    def _verstuur(self, tenant_id: int, bestand_id: str) -> str:
        if self.verstuur_fout is not None:
            raise self.verstuur_fout
        self.verstuurd.append((tenant_id, bestand_id))
        return f"bericht-{len(self.verstuurd)}"

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

        # Vervangen worden alleen de login en de rechtentoets zelf (`_toets_*`); de afhankelijkheid
        # `require_receipts_*` die de gebruiker op het verzoek zet voor de snelheidsbegrenzing is ECHT.
        app.dependency_overrides[get_db] = _mock_db
        app.dependency_overrides[get_current_user] = lambda: _gebruiker(tenant_id)
        app.dependency_overrides[_toets_write] = lambda: 1
        app.dependency_overrides[_toets_read] = lambda: 1
        if csrf_aan is False:
            app.dependency_overrides[validate_csrf_token] = lambda: None
        app.dependency_overrides[get_bon_dienst] = lambda: self.dienst
        return TestClient(app)

    def bestanden(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


@pytest.fixture(autouse=True)
def _leeg_de_snelheidsbegrenzing() -> Iterator[None]:
    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


@pytest.fixture
def s(tmp_path: Path) -> _Systeem:
    return _Systeem(tmp_path)


def _upload(client: TestClient, naam: str = "bon.pdf", inhoud: bytes = PDF, **extra: object):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/bonnen",
        files={"file": (naam, BytesIO(inhoud), "application/pdf")},
        **extra,  # type: ignore[arg-type]
    )


class TestUploaden:
    def test_an_upload_is_accepted_with_201_and_waiting(self, s: _Systeem) -> None:
        antwoord = _upload(s.client(1))

        assert (antwoord.status_code, antwoord.json()["data"]["status"]) == (201, "wachten")

    def test_the_answer_has_the_standard_shape(self, s: _Systeem) -> None:
        antwoord = _upload(s.client(1)).json()

        assert antwoord["success"] is True and set(antwoord["data"]) == {"bestand_id", "status"}

    def test_the_file_is_stored_under_the_tenant_of_the_logged_in_user(self, s: _Systeem) -> None:
        bestand_id = _upload(s.client(5)).json()["data"]["bestand_id"]

        assert (s.root / "5" / bestand_id).read_bytes() == PDF

    def test_a_tenant_id_in_the_request_is_ignored(self, s: _Systeem) -> None:
        antwoord = _upload(s.client(5), params={"tenant_id": 9}, data={"tenant_id": "9"})
        bestand_id = antwoord.json()["data"]["bestand_id"]

        assert (s.verstuurd, (s.root / "5" / bestand_id).exists()) == ([(5, bestand_id)], True)

    def test_the_order_for_the_worker_carries_the_tenant_of_the_user(self, s: _Systeem) -> None:
        _upload(s.client(5))

        assert s.verstuurd[0][0] == 5

    def test_the_answer_does_not_show_a_path_or_the_original_name(self, s: _Systeem) -> None:
        tekst = _upload(s.client(1), naam="geheim-salaris.pdf").text

        assert "geheim" not in tekst and str(s.root) not in tekst

    def test_a_file_that_is_too_large_is_413_and_leaves_nothing(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.als.bonlezer import upload as upload_module

        monkeypatch.setattr(upload_module, "MAX_BYTES", 10)

        antwoord = _upload(s.client(1))

        assert (antwoord.status_code, s.bestanden()) == (413, [])

    def test_a_file_of_the_wrong_type_is_415_and_leaves_nothing(self, s: _Systeem) -> None:
        antwoord = _upload(s.client(1), naam="bon.exe")

        assert (antwoord.status_code, s.bestanden()) == (415, [])

    def test_above_the_quota_the_answer_is_429_with_a_dutch_message(self, s: _Systeem) -> None:
        client = s.client(1)
        for _ in range(MAX_OPENSTAAND):
            _upload(client)

        antwoord = _upload(client)

        assert (
            antwoord.status_code,
            "Probeer het over een paar minuten opnieuw" in antwoord.text,
        ) == (429, True)

    def test_when_the_worker_cannot_be_reached_the_answer_is_503_and_nothing_stays(
        self, s: _Systeem
    ) -> None:
        s.verstuur_fout = ConnectionError("redis weg")

        antwoord = _upload(s.client(1))

        assert (antwoord.status_code, s.bestanden()) == (503, [])

    def test_the_upload_is_read_with_a_bound_of_one_byte_over_the_maximum(
        self, s: _Systeem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Geen onbegrensde `file.read()`: een enorm bestand komt niet volledig in het geheugen."""
        import importlib

        router_module = importlib.import_module("src.core.api.v1.bonnen.router")
        monkeypatch.setattr(router_module, "MAX_BYTES", 10)
        gezien: list[int] = []
        origineel = s.dienst.uploaden

        def vang(tenant_id: int, naam: str, inhoud: bytes) -> str:
            gezien.append(len(inhoud))
            return origineel(tenant_id, naam, inhoud)

        s.dienst.uploaden = vang  # type: ignore[method-assign]

        _upload(s.client(1), inhoud=PDF * 100)

        assert gezien == [11]

    def test_the_rate_limit_is_per_user_and_not_per_address(self, s: _Systeem) -> None:
        """Code- en security-review ronde 2: de sleutel moest uit de gebruiker komen, niet uit het IP.

        Twee gebruikers op HETZELFDE adres (de testclient heeft een vaste host): de eerste put zijn
        minuut op, de tweede mag nog gewoon uploaden.
        """
        eerste, tweede = s.client(1), s.client(2)
        for _ in range(12):
            _upload(eerste, naam="bon.exe")

        assert (
            _upload(eerste, naam="bon.exe").status_code,
            _upload(tweede, naam="bon.exe").status_code,
        ) == (429, 415)

    def test_the_limiter_key_contains_the_tenant_and_the_user(self, s: _Systeem) -> None:
        _upload(s.client(7))  # gebruiker 17 (10 + tenant) van tenant 7

        assert any(sleutel.startswith("7:u17:") for sleutel in _rate_limiter._requests)

    def test_the_message_of_an_error_is_plain_dutch_text(self, s: _Systeem) -> None:
        """Code-review ronde 1: `error.message` was een dict in plaats van tekst."""
        antwoord = _upload(s.client(1), naam="bon.exe").json()

        assert (
            isinstance(antwoord["error"]["message"], str)
            and "toegestaan" in antwoord["error"]["message"]
        )

    def test_too_many_uploads_in_a_minute_get_429_even_when_they_are_refused(
        self, s: _Systeem
    ) -> None:
        """Security-review ronde 1: een slot vrijmaken door te blijven vragen is geen quotum.

        Geweigerde uploads tellen mee voor de snelheidsbegrenzing per gebruiker (12 per minuut),
        zodat de begrenzing niet afhangt van het quotum op openstaande opdrachten.
        """
        client = s.client(1)

        statussen = [_upload(client, naam="bon.exe").status_code for _ in range(14)]

        assert statussen == [415] * 12 + [429, 429]

    def test_without_a_file_the_answer_is_422(self, s: _Systeem) -> None:
        assert s.client(1).post("/api/v1/bonnen").status_code == 422


class TestDeStatus:
    def test_the_status_of_an_upload_is_waiting_until_the_worker_is_done(self, s: _Systeem) -> None:
        client = s.client(1)
        bestand_id = _upload(client).json()["data"]["bestand_id"]

        antwoord = client.get(f"/api/v1/bonnen/{bestand_id}")

        assert (antwoord.status_code, antwoord.json()["data"]["status"]) == (200, "wachten")

    def test_another_tenant_gets_404_for_the_upload_of_tenant_a(self, s: _Systeem) -> None:
        bestand_id = _upload(s.client(1)).json()["data"]["bestand_id"]

        assert s.client(2).get(f"/api/v1/bonnen/{bestand_id}").status_code == 404

    def test_an_unknown_id_gets_404(self, s: _Systeem) -> None:
        assert s.client(1).get("/api/v1/bonnen/" + "0" * 32 + ".pdf").status_code == 404

    def test_an_id_of_another_shape_gets_404(self, s: _Systeem) -> None:
        assert s.client(1).get("/api/v1/bonnen/niet-een-id").status_code == 404

    def test_a_read_result_is_shown_with_its_fields(self, s: _Systeem) -> None:
        client = s.client(1)
        bestand_id = _upload(client).json()["data"]["bestand_id"]
        s.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": {"totaal": "12.10"},
        }

        data = client.get(f"/api/v1/bonnen/{bestand_id}").json()["data"]

        assert (data["status"], data["velden"]) == ("gelezen", {"totaal": "12.10"})

    def test_a_result_with_another_hash_than_the_upload_is_not_shown(self, s: _Systeem) -> None:
        client = s.client(1)
        bestand_id = _upload(client).json()["data"]["bestand_id"]
        s.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(b"iets anders").hexdigest(),
            "velden": {"totaal": "999.00"},
        }

        antwoord = client.get(f"/api/v1/bonnen/{bestand_id}")

        assert (antwoord.json()["data"]["status"], "999.00" in antwoord.text) == ("ongeldig", False)

    def test_the_answer_has_the_standard_shape(self, s: _Systeem) -> None:
        client = s.client(1)
        bestand_id = _upload(client).json()["data"]["bestand_id"]

        assert client.get(f"/api/v1/bonnen/{bestand_id}").json()["success"] is True


async def _mock_db() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()


class TestDeToegang:
    def test_the_upload_route_asks_for_a_login(self) -> None:
        app = FastAPI()
        app.include_router(bonnen_router)
        app.dependency_overrides[get_bon_dienst] = lambda: None
        app.dependency_overrides[get_db] = _mock_db

        antwoord = TestClient(app).post(
            "/api/v1/bonnen", files={"file": ("bon.pdf", BytesIO(PDF), "application/pdf")}
        )

        assert antwoord.status_code in (401, 403)

    def test_the_status_route_asks_for_a_login(self) -> None:
        app = FastAPI()
        app.include_router(bonnen_router)
        app.dependency_overrides[get_bon_dienst] = lambda: None
        app.dependency_overrides[get_db] = _mock_db

        assert TestClient(app).get("/api/v1/bonnen/" + "0" * 32 + ".pdf").status_code in (401, 403)
