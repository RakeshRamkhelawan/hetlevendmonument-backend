"""De verbindingspaden van service en client tegen een ECHTE ActivePieces 0.92.1.

SP-KOPPEL-001 dag 1. Dit toetst niet wat wij DENKEN dat AP doet maar wat AP antwoordt: service en
client doen hun aanroepen tegen een draaiende AP, en de oude paden worden rechtstreeks bevraagd
om vast te leggen dat ze er NIET zijn.

Gemeten op 2026-10-25 tegen `ghcr.io/activepieces/activepieces:0.92.1` (wegwerpcontainer met eigen
Postgres en Redis):

- `/connections`, `/connections/{id}`, `/connections/{id}/test` en `/connections/oauth/...`:
  allemaal 404.
- `GET /app-connections` 200; `POST /app-connections` 201 (maakt of vervangt op `externalId`);
  `GET`/`POST`/`DELETE /app-connections/{id}` 200/200/204; `POST /app-connections/{id}/test` 404.

Draaien tegen een lokale AP:

    AP_METING_URL=http://127.0.0.1:18081/api/v1 python -m pytest \\
        tests/integration/test_ap_verbindingspaden_kloppen.py -m integration

Zonder `AP_METING_URL` slaat de module zichzelf over: er is dan geen AP om te meten, en dit is
GEEN onderdeel van de testpoort. De test maakt zijn eigen gebruiker en project aan op die AP.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.schemas import ConnectionCreate
from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.verbinding import ApRessourceNietGevondenError, ApVerbinding

pytestmark = pytest.mark.integration

_URL = os.environ.get("AP_METING_URL", "")
_WACHTWOORD = "Meting-" + uuid.uuid4().hex[:12] + "-Aa1!"

if not _URL:
    pytest.skip(
        "AP_METING_URL is niet gezet: er is geen draaiende AP om tegen te meten",
        allow_module_level=True,
    )


@pytest_asyncio.fixture
async def ap_toegang() -> AsyncIterator[tuple[str, str, str, dict[str, str]]]:
    """Een gebruiker en project op de AP: (project_id, e-mail, wachtwoord, kopregels).

    Op een verse AP maakt de test zelf de eerste gebruiker aan. Een AP staat maar een aanmelding
    toe (daarna 403); dan geef je een bestaande gebruiker op met `AP_METING_EMAIL` en
    `AP_METING_WACHTWOORD`. Lukt geen van beide, dan FAALT de test: een overgeslagen meting
    bewijst niets.
    """
    email = os.environ.get("AP_METING_EMAIL", "")
    wachtwoord = os.environ.get("AP_METING_WACHTWOORD", "")
    async with httpx.AsyncClient(timeout=60) as http:
        if email and wachtwoord:
            antwoord = await http.post(
                f"{_URL}/authentication/sign-in", json={"email": email, "password": wachtwoord}
            )
        else:
            email, wachtwoord = f"meting-{uuid.uuid4().hex[:10]}@example.test", _WACHTWOORD
            antwoord = await http.post(
                f"{_URL}/authentication/sign-up",
                json={
                    "email": email,
                    "password": wachtwoord,
                    "firstName": "Meting",
                    "lastName": "Koppel",
                    "trackEvents": False,
                    "newsLetter": False,
                },
            )
        assert antwoord.status_code == 200, (
            f"geen toegang tot de AP (status {antwoord.status_code}); gebruik een verse AP of "
            "zet AP_METING_EMAIL en AP_METING_WACHTWOORD"
        )
        data = antwoord.json()
    yield data["projectId"], email, wachtwoord, {"Authorization": f"Bearer {data['token']}"}


@pytest.fixture
def dienst(ap_toegang: tuple[str, str, str, dict[str, str]]) -> ActivePiecesService:
    project_id, email, wachtwoord, _ = ap_toegang
    client = ActivePiecesClient(
        ApVerbinding(
            tenant_id=9001,
            base_url=_URL,
            email=email,
            wachtwoord=wachtwoord,
            project_id=project_id,
        )
    )
    return ActivePiecesService(client=client)


def _nieuw(naam: str) -> ConnectionCreate:
    return ConnectionCreate(name=naam, app_name="http", project_id=None, value={"type": "NO_AUTH"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "methode,pad",
    [
        ("GET", "/connections"),
        ("POST", "/connections"),
        ("GET", "/connections/x"),
        ("POST", "/connections/x"),
        ("DELETE", "/connections/x"),
        ("POST", "/connections/x/test"),
        ("POST", "/connections/oauth/slack/url"),
        ("POST", "/connections/oauth/callback"),
        ("POST", "/app-connections/x/test"),
    ],
)
async def test_de_oude_paden_bestaan_niet_bij_ap(
    ap_toegang: tuple[str, str, str, dict[str, str]], methode: str, pad: str
) -> None:
    _, _, _, kopregels = ap_toegang
    async with httpx.AsyncClient(timeout=60) as http:
        antwoord = await http.request(methode, f"{_URL}{pad}", headers=kopregels, json={})

    assert antwoord.status_code == 404


@pytest.mark.asyncio
async def test_een_verbinding_gaat_door_de_hele_levensloop_via_de_service(
    dienst: ActivePiecesService,
) -> None:
    aangemaakt = await dienst.create_connection(_nieuw("meting een"))
    lijst_na_aanmaken = [v.id for v in await dienst.list_connections()]
    opgehaald = await dienst.get_connection(aangemaakt.id)
    herdoopt = await dienst.update_connection(aangemaakt.id, name="meting twee")
    getest = await dienst.test_connection(aangemaakt.id)
    await dienst.delete_connection(aangemaakt.id)
    lijst_na_verwijderen = [v.id for v in await dienst.list_connections()]

    assert (
        aangemaakt.id in lijst_na_aanmaken,
        opgehaald.name,
        herdoopt.name,
        getest["success"],
        aangemaakt.id in lijst_na_verwijderen,
    ) == (True, "meting een", "meting twee", True, False)


@pytest.mark.asyncio
async def test_een_verwijderde_verbinding_geeft_404_bij_ophalen(
    dienst: ActivePiecesService,
) -> None:
    aangemaakt = await dienst.create_connection(_nieuw("meting weg"))
    await dienst.delete_connection(aangemaakt.id)

    with pytest.raises(ApRessourceNietGevondenError):
        await dienst.get_connection(aangemaakt.id)


@pytest.mark.asyncio
async def test_twee_verbindingen_met_dezelfde_naam_blijven_twee_verbindingen(
    dienst: ActivePiecesService,
) -> None:
    eerste = await dienst.create_connection(_nieuw("zelfde naam"))
    tweede = await dienst.create_connection(_nieuw("zelfde naam"))

    ids = {v.id for v in await dienst.list_connections()}
    assert {eerste.id, tweede.id} <= ids and eerste.id != tweede.id


@pytest.mark.asyncio
async def test_een_rename_via_de_service_houdt_de_verbinding_actief(
    dienst: ActivePiecesService,
) -> None:
    aangemaakt = await dienst.create_connection(_nieuw("voor rename"))

    await dienst.update_connection(aangemaakt.id, name="na rename")

    assert (await dienst.test_connection(aangemaakt.id))["success"] is True
