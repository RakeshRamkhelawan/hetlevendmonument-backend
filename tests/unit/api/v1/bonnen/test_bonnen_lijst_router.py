"""De lijst van bonnen via de route (acceptatie dag 4): bestandsnaam, leverancier, stand en "controleren".

De regels zitten in `BonBevestiging.lijst` (`tests/unit/bonlezer/test_controleren_en_lijst.py`); hier alleen
de HTTP-laag: een bon die niemand heeft geopend krijgt bij het ophalen van de lijst alsnog zijn
leesresultaat, en de tenant komt uit de ingelogde gebruiker.

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
VELDEN = {
    "leverancier": "Bloemgracht",
    "datum": "2026-10-01",
    "totaal": "16.15",
    "factuurnummer": None,
    "btw": {"9": "1.33"},
    "btw_nummer": None,
    "kvk_nummer": None,
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

    def client(self, tenant_id: int) -> TestClient:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(bonnen_router)

        async def _mock_db() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        app.dependency_overrides[get_db] = _mock_db
        app.dependency_overrides[get_current_user] = lambda: _gebruiker(tenant_id)
        app.dependency_overrides[_toets_write] = lambda: 1
        app.dependency_overrides[_toets_read] = lambda: 1
        app.dependency_overrides[validate_csrf_token] = lambda: None
        app.dependency_overrides[get_bon_dienst] = lambda: self.dienst
        app.dependency_overrides[get_bon_bevestiging] = lambda: self.bevestiging
        return TestClient(app)

    def ongeopende_bon(self, naam: str = "bon_12.jpg.pdf", tenant_id: int = 1) -> str:
        bestand_id = self.dienst.uploaden(tenant_id, naam, PDF)
        self.resultaten[f"bericht-{self.verstuurd}"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": dict(VELDEN),
        }
        return bestand_id


@pytest.fixture(autouse=True)
def _leeg_de_snelheidsbegrenzing() -> Iterator[None]:
    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


@pytest.fixture
def s(tmp_path: Path) -> _Systeem:
    return _Systeem(tmp_path)


def _items(antwoord: object) -> list[dict[str, object]]:
    return antwoord.json()["data"]["items"]  # type: ignore[attr-defined,no-any-return]


class TestDeLijstViaDeRoute:
    def test_a_bon_nobody_opened_gets_its_result_when_the_list_is_fetched(
        self, s: _Systeem
    ) -> None:
        s.ongeopende_bon()

        item = _items(s.client(1).get("/api/v1/bonnen"))[0]

        assert (item["status"], item["leverancier"]) == ("gelezen", "Bloemgracht")

    def test_the_file_name_is_in_the_list(self, s: _Systeem) -> None:
        s.ongeopende_bon(naam="bon_12.jpg.pdf")

        assert _items(s.client(1).get("/api/v1/bonnen"))[0]["naam"] == "bon_12.jpg.pdf"

    def test_a_bon_with_empty_numbers_is_flagged_in_the_list(self, s: _Systeem) -> None:
        s.ongeopende_bon()

        assert _items(s.client(1).get("/api/v1/bonnen"))[0]["controleren"] is True

    def test_the_result_is_stored_after_the_list_was_fetched(self, s: _Systeem) -> None:
        bestand_id = s.ongeopende_bon()

        s.client(1).get("/api/v1/bonnen")

        assert (s.root / "1" / f"{bestand_id}.resultaat.json").is_file()

    def test_another_tenant_does_not_see_the_bon(self, s: _Systeem) -> None:
        s.ongeopende_bon()

        assert _items(s.client(2).get("/api/v1/bonnen")) == []

    def test_a_broken_result_store_does_not_break_the_list(self, s: _Systeem) -> None:
        s.ongeopende_bon()

        def _stuk(message_id: str) -> dict[str, object]:
            raise ConnectionError("redis weg")

        s.dienst = BonDienst(s.root, verstuur=s._verstuur, haal=_stuk)

        antwoord = s.client(1).get("/api/v1/bonnen")

        assert (antwoord.status_code, len(_items(antwoord))) == (200, 1)
