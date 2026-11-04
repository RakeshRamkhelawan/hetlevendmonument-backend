"""De koppelroutes van ActivePieces: schrijven alleen voor de beheerder, met een logboekregel.

SP-KOPPEL-001 dag 1. Gemeten voor de fix (code gelezen): elke ingelogde gebruiker mocht een
verbinding aanmaken, wijzigen, testen en verwijderen, en er werd niets vastgelegd.

De tests draaien over de ECHTE router in een kleine app. Alleen de grenzen zijn vervangen: de
ingelogde gebruiker, de tenant uit het token, de database en de ActivePieces-service.
`log_security_event` wordt op de plek van gebruik opgevangen, zodat we zien wat er in het
logboek terechtkomt.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.activepieces.client import get_activepieces_client
from src.core.activepieces.schemas import ConnectionRead
from src.core.activepieces.service import get_activepieces_service
from src.core.api.v1.activepieces import connections_router
from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db
from src.core.exceptions.handlers import register_exception_handlers
from src.core.middleware.tenant_context import safe_get_tenant_id

pytestmark = pytest.mark.unit

_AUDIT = "src.core.activepieces.koppel_toegang.log_security_event"
_GEHEIM = "geheime-waarde-voor-de-test-123"

MEDEWERKER = SimpleNamespace(id=7, email="m@a.test", roles=["employee"], is_superuser=False)
BEHEERDER = SimpleNamespace(id=8, email="b@a.test", roles=["admin"], is_superuser=False)

_TIJD = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
_AANMAKEN = {"name": "n", "app_name": "slack", "value": {"token": _GEHEIM}}
_SCHRIJFROUTES = [
    ("POST", "/integrations/connections", _AANMAKEN),
    ("PUT", "/integrations/connections/conn-1", {"name": "nieuw", "value": {"token": _GEHEIM}}),
    ("POST", "/integrations/connections/conn-1/test", None),
    ("DELETE", "/integrations/connections/conn-1", None),
]


def _verbinding(verbinding_id: str = "conn-1") -> ConnectionRead:
    return ConnectionRead(
        id=verbinding_id,
        name="mijn slack",
        app_name="slack",
        project_id="proj-a",
        value={},
        created=_TIJD,
        updated=_TIJD,
    )


def _dienst() -> MagicMock:
    dienst = MagicMock()
    dienst.list_connections = AsyncMock(return_value=[_verbinding()])
    dienst.get_connection = AsyncMock(return_value=_verbinding())
    dienst.create_connection = AsyncMock(return_value=_verbinding())
    dienst.update_connection = AsyncMock(return_value=_verbinding())
    dienst.delete_connection = AsyncMock(return_value=None)
    dienst.test_connection = AsyncMock(
        return_value={"success": True, "message": "ok", "details": None}
    )
    return dienst


def _client(gebruiker: SimpleNamespace, dienst: MagicMock, tenant_id: int = 1) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(connections_router.router)
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[get_activepieces_service] = lambda: dienst
    app.dependency_overrides[safe_get_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _schone_limiter() -> Iterator[None]:
    """De limiet werkt echt (10 schrijfaanroepen per minuut); elke test begint met een lege teller."""
    from src.core.shared.rate_limiter import _rate_limiter

    _rate_limiter._requests.clear()
    yield
    _rate_limiter._requests.clear()


@pytest.fixture(name="_audit_standaard_opvangen", autouse=True)
def audit_opvangen() -> Iterator[AsyncMock]:
    with patch(_AUDIT, new=AsyncMock()) as audit:
        yield audit


@pytest.mark.parametrize("methode,pad,body", _SCHRIJFROUTES)
def test_een_medewerker_krijgt_403_op_elke_schrijfroute(
    methode: str, pad: str, body: dict[str, object] | None
) -> None:
    client = _client(MEDEWERKER, _dienst())

    antwoord = client.request(methode, pad, json=body)

    assert antwoord.status_code == 403


def test_de_403_voor_een_medewerker_noemt_de_beheerder() -> None:
    client = _client(MEDEWERKER, _dienst())

    antwoord = client.delete("/integrations/connections/conn-1")

    assert "beheerder" in antwoord.json()["detail"].lower()


def test_een_geweigerde_medewerker_raakt_activepieces_niet_aan() -> None:
    dienst = _dienst()
    client = _client(MEDEWERKER, dienst)

    client.delete("/integrations/connections/conn-1")

    assert dienst.delete_connection.await_count == 0


def test_een_geweigerde_medewerker_laat_geen_auditregel_achter(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    client = _client(MEDEWERKER, _dienst())

    client.delete("/integrations/connections/conn-1")

    assert _audit_standaard_opvangen.await_count == 0


def test_een_medewerker_mag_de_lijst_lezen() -> None:
    client = _client(MEDEWERKER, _dienst())

    antwoord = client.get("/integrations/connections")

    assert antwoord.status_code == 200


def test_een_medewerker_mag_een_verbinding_ophalen() -> None:
    client = _client(MEDEWERKER, _dienst())

    antwoord = client.get("/integrations/connections/conn-1")

    assert antwoord.status_code == 200


@pytest.mark.parametrize(
    "route,verwacht", list(zip(_SCHRIJFROUTES, [201, 200, 200, 200], strict=True))
)
def test_een_beheerder_blijft_alles_kunnen(
    route: tuple[str, str, dict[str, object] | None], verwacht: int
) -> None:
    methode, pad, body = route
    client = _client(BEHEERDER, _dienst())

    antwoord = client.request(methode, pad, json=body)

    assert antwoord.status_code == verwacht


@pytest.mark.parametrize(
    "route,gebeurtenis",
    [
        (_SCHRIJFROUTES[0], "AP_VERBINDING_AANGEMAAKT"),
        (_SCHRIJFROUTES[1], "AP_VERBINDING_GEWIJZIGD"),
        (_SCHRIJFROUTES[3], "AP_VERBINDING_VERWIJDERD"),
    ],
)
def test_aanmaken_wijzigen_en_verwijderen_schrijven_een_auditregel(
    route: tuple[str, str, dict[str, object] | None],
    gebeurtenis: str,
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    methode, pad, body = route
    client = _client(BEHEERDER, _dienst(), tenant_id=5)

    client.request(methode, pad, json=body)

    assert _audit_standaard_opvangen.await_args is not None
    kwargs = _audit_standaard_opvangen.await_args.kwargs
    assert (kwargs["event_type"], kwargs["user_id"], kwargs["tenant_id"]) == (gebeurtenis, 8, 5)


@pytest.mark.parametrize("route", [_SCHRIJFROUTES[0], _SCHRIJFROUTES[1], _SCHRIJFROUTES[3]])
def test_de_auditregel_bevat_nooit_de_sleutel(
    route: tuple[str, str, dict[str, object] | None],
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    methode, pad, body = route
    client = _client(BEHEERDER, _dienst())

    client.request(methode, pad, json=body)

    assert _audit_standaard_opvangen.await_args is not None
    assert _GEHEIM not in json.dumps(_audit_standaard_opvangen.await_args.kwargs, default=str)


def test_de_auditregel_noemt_het_piece_en_de_verbinding(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    client = _client(BEHEERDER, _dienst())

    client.post("/integrations/connections", json=_AANMAKEN)

    assert _audit_standaard_opvangen.await_args is not None
    details = _audit_standaard_opvangen.await_args.kwargs["details"]
    assert (details["app_name"], details["connection_id"]) == ("slack", "conn-1")


def test_een_mislukte_verwijdering_schrijft_geen_auditregel(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    dienst = _dienst()
    dienst.delete_connection = AsyncMock(side_effect=RuntimeError("AP is weg"))
    client = _client(BEHEERDER, dienst)

    client.delete("/integrations/connections/conn-1")

    assert _audit_standaard_opvangen.await_count == 0


def test_een_auditregel_die_faalt_laat_de_verwijdering_slagen(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    _audit_standaard_opvangen.side_effect = RuntimeError("db weg")
    client = _client(BEHEERDER, _dienst())

    antwoord = client.delete("/integrations/connections/conn-1")

    assert antwoord.status_code == 200


def test_een_beheerder_van_klant_a_wijzigt_geen_verbinding_van_klant_b() -> None:
    from src.core.activepieces.verbinding import ApRessourceNietGevondenError

    dienst = _dienst()
    dienst.update_connection = AsyncMock(side_effect=ApRessourceNietGevondenError("Verbinding"))
    client = _client(BEHEERDER, dienst, tenant_id=1)

    antwoord = client.put("/integrations/connections/van-klant-b", json={"name": "x"})

    assert antwoord.status_code == 404


def test_een_beheerder_van_klant_a_verwijdert_geen_verbinding_van_klant_b(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    from src.core.activepieces.verbinding import ApRessourceNietGevondenError

    dienst = _dienst()
    dienst.delete_connection = AsyncMock(side_effect=ApRessourceNietGevondenError("Verbinding"))
    client = _client(BEHEERDER, dienst, tenant_id=1)

    antwoord = client.delete("/integrations/connections/van-klant-b")

    assert (antwoord.status_code, _audit_standaard_opvangen.await_count) == (404, 0)


_OAUTH_URL = "/integrations/connections/oauth/slack/url?redirect_uri=https://a.example/terug"
_OAUTH_TERUG = "/integrations/connections/oauth/callback?app_name=slack&code=c&state=s"


@pytest.mark.parametrize("methode,pad", [("GET", _OAUTH_URL), ("POST", _OAUTH_TERUG)])
def test_een_medewerker_krijgt_403_op_de_oauth_routes(methode: str, pad: str) -> None:
    client = _client(MEDEWERKER, _dienst())

    antwoord = client.request(methode, pad)

    assert antwoord.status_code == 403


def test_een_beheerder_komt_langs_de_oauth_terugkeer_en_laat_een_auditregel_achter(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    ap_client = MagicMock()
    ap_client.eigen_project = MagicMock(return_value="proj-a")
    ap_client._make_request = AsyncMock(return_value={"id": "nieuw-1"})
    app = _client(BEHEERDER, _dienst()).app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_activepieces_client] = lambda: ap_client

    antwoord = TestClient(app).post(_OAUTH_TERUG)

    assert (antwoord.status_code, _audit_standaard_opvangen.await_count) == (200, 1)


def test_een_medewerker_krijgt_403_ook_als_de_ap_koppeling_van_de_klant_ontbreekt() -> None:
    """De rolcontrole komt VOOR het opbouwen van de AP-dienst (die ontsleutelt het AP-wachtwoord)."""
    from fastapi import HTTPException

    def _zonder_ap_koppeling() -> MagicMock:
        raise HTTPException(status_code=409, detail="Geen AP-verbinding")

    client = _client(MEDEWERKER, _dienst())
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_activepieces_service] = _zonder_ap_koppeling

    antwoord = client.delete("/integrations/connections/conn-1")

    assert antwoord.status_code == 403


def test_de_auditregel_bevat_geen_vrije_tekst_van_de_beheerder(
    _audit_standaard_opvangen: AsyncMock,
) -> None:
    """Een beheerder kan een geheim in de naam typen; die hoort niet in het logboek."""
    client = _client(BEHEERDER, _dienst())

    client.post("/integrations/connections", json=_AANMAKEN)

    assert _audit_standaard_opvangen.await_args is not None
    assert "connection_name" not in _audit_standaard_opvangen.await_args.kwargs["details"]
