"""De routes voor het btw-overzicht per kwartaal (btw-overzicht, 2026-10-19).

`GET /api/v1/bonnen/btw-overzicht?kwartaal=2026-Q3` en `GET /api/v1/bonnen/btw-overzicht.csv?kwartaal=...`
(`receipts:read`). De regels (kwartaal, afronding, alleen bevestigd) staan in
`tests/unit/bonlezer/test_btw_overzicht.py`; hier alleen de HTTP-laag: de tenant uit de ingelogde gebruiker
(nooit uit de query), het standaardkwartaal, de statuscodes en de CSV-kop.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Iterator
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.als.bonlezer.btw_overzicht import BtwOverzicht
from src.core.api.v1.bonnen.dependencies import (
    _toets_read,
    _toets_write,
    get_btw_overzicht,
    get_current_user,
    get_nu,
)
from src.core.api.v1.bonnen.router import router as bonnen_router
from src.core.auth.auth_service import UserResponse
from src.core.database.database import get_db
from src.core.exceptions.handlers import register_exception_handlers
from src.core.shared.rate_limiter import _rate_limiter

pytestmark = pytest.mark.unit

NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
URL = "/api/v1/bonnen/btw-overzicht"


def _gebruiker(tenant_id: int) -> UserResponse:
    return UserResponse(
        id=10 + tenant_id, email="a@example.test", tenant_id=tenant_id, roles=["user"]
    )


def _bevestig(root: Path, tenant: int, teken: str, datum: str, btw: dict[str, str]) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden = {
        "leverancier": "Bakkerij De Korenaar B.V.",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw,
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    (map_ / f"{teken * 32}.pdf.bevestigd.json").write_text(
        json.dumps({"velden": velden, "door": 1, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )


class _Systeem:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.overzicht = BtwOverzicht(root)

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
        app.dependency_overrides[get_btw_overzicht] = lambda: self.overzicht
        app.dependency_overrides[get_nu] = lambda: NU
        return TestClient(app)


@pytest.fixture(autouse=True)
def _leeg_de_snelheidsbegrenzing() -> Iterator[None]:
    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


@pytest.fixture
def s(tmp_path: Path) -> _Systeem:
    return _Systeem(tmp_path)


def _data(antwoord: object) -> dict[str, object]:
    return antwoord.json()["data"]  # type: ignore[attr-defined,no-any-return]


class TestHetOverzicht:
    def test_three_bonnen_in_q3_and_one_in_q4_give_the_q3_overview(self, s: _Systeem) -> None:
        _bevestig(s.root, 1, "a", "2026-07-15", {"9": "0.50", "21": "1.60"})
        _bevestig(s.root, 1, "b", "2026-08-20", {"21": "2.10"})
        _bevestig(s.root, 1, "c", "2026-09-30", {"9": "1.25"})
        _bevestig(s.root, 1, "d", "2026-10-01", {"9": "99.00"})

        antwoord = s.client(1).get(URL, params={"kwartaal": "2026-Q3"})

        assert (antwoord.status_code, _data(antwoord)["aantal"], _data(antwoord)["totaal"]) == (
            200,
            3,
            "5.45",
        )

    def test_the_answer_has_the_standard_shape(self, s: _Systeem) -> None:
        antwoord = s.client(1).get(URL, params={"kwartaal": "2026-Q3"})

        assert antwoord.json()["success"] is True

    def test_without_a_quarter_the_current_quarter_is_used(self, s: _Systeem) -> None:
        _bevestig(s.root, 1, "a", "2026-10-05", {"21": "3.00"})

        antwoord = s.client(1).get(URL)

        assert (_data(antwoord)["kwartaal"], _data(antwoord)["aantal"]) == ("2026-Q4", 1)

    def test_an_invalid_quarter_is_a_422_with_dutch_text(self, s: _Systeem) -> None:
        antwoord = s.client(1).get(URL, params={"kwartaal": "2026-Q5"})

        assert antwoord.status_code == 422 and "kwartaal" in antwoord.text.lower()

    def test_an_empty_quarter_is_a_200_with_zero(self, s: _Systeem) -> None:
        antwoord = s.client(1).get(URL, params={"kwartaal": "2026-Q1"})

        assert (antwoord.status_code, _data(antwoord)["totaal"]) == (200, "0.00")

    def test_the_tenant_comes_from_the_user_and_not_from_the_query(self, s: _Systeem) -> None:
        _bevestig(s.root, 2, "a", "2026-08-01", {"21": "50.00"})

        antwoord = s.client(1).get(URL, params={"kwartaal": "2026-Q3", "tenant_id": 2})

        assert _data(antwoord)["aantal"] == 0

    def test_another_tenant_sees_nothing_of_this_tenant(self, s: _Systeem) -> None:
        _bevestig(s.root, 1, "a", "2026-08-01", {"21": "50.00"})

        assert _data(s.client(2).get(URL, params={"kwartaal": "2026-Q3"}))["aantal"] == 0

    def test_the_path_is_not_read_as_a_bon_id(self, s: _Systeem) -> None:
        assert s.client(1).get(URL).status_code != 404

    def test_the_61st_read_in_a_minute_is_429(self, s: _Systeem) -> None:
        client = s.client(1)

        statussen = [client.get(URL).status_code for _ in range(61)]

        assert statussen[-1] == 429


class TestDeCsv:
    def test_the_csv_has_the_right_type_and_name(self, s: _Systeem) -> None:
        antwoord = s.client(1).get(f"{URL}.csv", params={"kwartaal": "2026-Q3"})

        assert (
            antwoord.status_code,
            antwoord.headers["content-type"].startswith("text/csv"),
            antwoord.headers["content-disposition"],
        ) == (200, True, 'attachment; filename="btw-overzicht-2026-Q3.csv"')

    def test_the_csv_contains_the_bonnen_of_the_quarter_and_the_totals(self, s: _Systeem) -> None:
        _bevestig(s.root, 1, "a", "2026-07-15", {"9": "0.50", "21": "1.60"})
        _bevestig(s.root, 1, "b", "2026-10-15", {"9": "9.00"})

        tekst = s.client(1).get(f"{URL}.csv", params={"kwartaal": "2026-Q3"}).text

        assert (
            "2026-07-15" in tekst and "2026-10-15" not in tekst and "Totaal voorbelasting" in tekst
        )

    def test_an_invalid_quarter_is_a_422(self, s: _Systeem) -> None:
        assert s.client(1).get(f"{URL}.csv", params={"kwartaal": "x"}).status_code == 422

    def test_without_a_quarter_the_current_quarter_is_used(self, s: _Systeem) -> None:
        antwoord = s.client(1).get(f"{URL}.csv")

        assert 'filename="btw-overzicht-2026-Q4.csv"' in antwoord.headers["content-disposition"]

    def test_another_tenant_gets_no_rows_of_this_tenant(self, s: _Systeem) -> None:
        _bevestig(s.root, 1, "a", "2026-07-15", {"9": "0.50"})

        tekst = s.client(2).get(f"{URL}.csv", params={"kwartaal": "2026-Q3"}).text

        assert "2026-07-15" not in tekst
