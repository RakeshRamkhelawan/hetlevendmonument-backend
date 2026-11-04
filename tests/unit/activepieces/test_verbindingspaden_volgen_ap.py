"""De verbindingspaden van service en client volgen wat ActivePieces 0.92.1 ECHT doet.

SP-KOPPEL-001 dag 1. Gemeten op 2026-10-25 tegen een draaiende AP 0.92.1 (zie
`tests/integration/test_ap_verbindingspaden_kloppen.py`): `/connections` en alles eronder geeft
404; de verbindingen staan onder `/app-connections`, met `displayName`, `pieceName` en een LIJST
`projectIds`. Er is geen testroute. Een rename (`POST /app-connections/{id}` met alleen
`displayName`) laat de opgeslagen waarde ongemoeid; een meegestuurde `value` wordt genegeerd.

Alleen HTTP naar AP is vervangen (respx), met antwoorden in de gemeten vorm.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import respx
from httpx import Response

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.schemas import ConnectionCreate
from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.verbinding import ApRessourceNietGevondenError, ApVerbinding
from src.core.exceptions import ValidatieFout

BASE_URL = "http://ap-paden.example.test/api/v1"
EIGEN = "proj-paden-eigen"
VREEMD = "proj-paden-vreemd"

pytestmark = pytest.mark.unit


@pytest.fixture
def dienst() -> ActivePiecesService:
    client = ActivePiecesClient(
        ApVerbinding(
            tenant_id=7,
            base_url=BASE_URL,
            email="ap@example.test",
            wachtwoord="geheim-voor-de-test",
            project_id=EIGEN,
        )
    )
    client.token = "t"
    return ActivePiecesService(client=client)


@pytest.fixture
def ap() -> Iterator[Any]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post("/authentication/sign-in").mock(return_value=Response(200, json={"token": "t"}))
        yield mock


def _item(
    project_ids: list[str], item_id: str = "c1", piece: str = "@activepieces/piece-http"
) -> dict[str, Any]:
    return {
        "id": item_id,
        "displayName": "mijn koppeling",
        "externalId": "ext-1",
        "pieceName": piece,
        "type": "NO_AUTH",
        "status": "ACTIVE",
        "projectIds": project_ids,
        "created": "2026-10-25T10:00:00.000Z",
        "updated": "2026-10-25T10:00:00.000Z",
    }


def _nieuw(
    naam: str = "mijn koppeling", waarde: dict[str, object] | None = None
) -> ConnectionCreate:
    return ConnectionCreate(
        name=naam, app_name="http", project_id=None, value=waarde or {"type": "NO_AUTH"}
    )


@pytest.mark.asyncio
async def test_de_lijst_geeft_alleen_verbindingen_van_het_eigen_project(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections").mock(
        return_value=Response(
            200,
            json={
                "data": [_item([EIGEN], "a"), _item([VREEMD], "b")],
                "next": None,
                "previous": None,
            },
        )
    )

    verbindingen = await dienst.list_connections()

    assert [v.id for v in verbindingen] == ["a"]


@pytest.mark.asyncio
async def test_de_lijst_laat_een_met_een_ander_project_gedeelde_verbinding_weg(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections").mock(
        return_value=Response(
            200,
            json={
                "data": [_item([EIGEN], "a"), _item([EIGEN, VREEMD], "gedeeld")],
                "next": None,
                "previous": None,
            },
        )
    )

    verbindingen = await dienst.list_connections()

    assert [v.id for v in verbindingen] == ["a"]


@pytest.mark.asyncio
async def test_de_lijst_volgt_de_cursor_van_ap_naar_de_volgende_pagina(
    dienst: ActivePiecesService, ap: Any
) -> None:
    """AP geeft standaard 10 verbindingen met een `next`-cursor (gemeten); de rest ontbrak."""
    route = ap.get("/app-connections")
    route.side_effect = [
        Response(200, json={"data": [_item([EIGEN], "a")], "next": "cursor-2", "previous": None}),
        Response(200, json={"data": [_item([EIGEN], "b")], "next": None, "previous": "x"}),
    ]

    verbindingen = await dienst.list_connections()

    assert [v.id for v in verbindingen] == ["a", "b"]


@pytest.mark.asyncio
async def test_de_tweede_paginavraag_draagt_de_cursor(dienst: ActivePiecesService, ap: Any) -> None:
    route = ap.get("/app-connections")
    route.side_effect = [
        Response(200, json={"data": [_item([EIGEN], "a")], "next": "cursor-2", "previous": None}),
        Response(200, json={"data": [], "next": None, "previous": None}),
    ]

    await dienst.list_connections()

    assert route.calls[1].request.url.params.get("cursor") == "cursor-2"


@pytest.mark.asyncio
async def test_de_lijst_toont_naam_en_kort_piece_zonder_sleutel(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections").mock(
        return_value=Response(200, json={"data": [_item([EIGEN])], "next": None, "previous": None})
    )

    verbinding = (await dienst.list_connections())[0]

    assert (verbinding.name, verbinding.app_name, verbinding.value) == (
        "mijn koppeling",
        "http",
        {},
    )


@pytest.mark.asyncio
async def test_ophalen_gebruikt_het_app_connections_pad(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))

    assert (await dienst.get_connection("c1")).id == "c1"


@pytest.mark.asyncio
async def test_aanmaken_stuurt_de_ap_vorm_naar_app_connections(
    dienst: ActivePiecesService, ap: Any
) -> None:
    aanroep = ap.post("/app-connections").mock(return_value=Response(201, json=_item([EIGEN])))

    await dienst.create_connection(_nieuw())

    body = json.loads(aanroep.calls.last.request.content)
    assert (body["displayName"], body["pieceName"], body["projectId"], body["type"]) == (
        "mijn koppeling",
        "@activepieces/piece-http",
        EIGEN,
        "NO_AUTH",
    )


@pytest.mark.asyncio
async def test_aanmaken_geeft_elke_verbinding_een_eigen_externalid(
    dienst: ActivePiecesService, ap: Any
) -> None:
    aanroep = ap.post("/app-connections").mock(return_value=Response(201, json=_item([EIGEN])))

    await dienst.create_connection(_nieuw("zelfde naam"))
    await dienst.create_connection(_nieuw("zelfde naam"))

    ids = {json.loads(c.request.content)["externalId"] for c in aanroep.calls}
    assert len(ids) == 2


@pytest.mark.asyncio
async def test_aanmaken_zonder_verbindingstype_is_een_validatiefout(
    dienst: ActivePiecesService, ap: Any
) -> None:
    with pytest.raises(ValidatieFout):
        await dienst.create_connection(_nieuw(waarde={"x": 1}))


@pytest.mark.asyncio
async def test_een_rename_stuurt_alleen_de_naam_en_geen_value(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    wijzigen = ap.post("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))

    await dienst.update_connection("c1", name="nieuwe naam")

    assert json.loads(wijzigen.calls.last.request.content) == {"displayName": "nieuwe naam"}


@pytest.mark.asyncio
async def test_een_nieuwe_sleutel_gaat_als_upsert_op_hetzelfde_externalid(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    upsert = ap.post("/app-connections").mock(return_value=Response(201, json=_item([EIGEN])))

    await dienst.update_connection("c1", name=None, value={"secret_text": "nieuw"})

    body = json.loads(upsert.calls.last.request.content)
    assert (body["externalId"], body["pieceName"], body["value"]["type"]) == (
        "ext-1",
        "@activepieces/piece-http",
        "NO_AUTH",
    )


@pytest.mark.asyncio
async def test_verwijderen_gebruikt_delete_op_app_connections(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    verwijderen = ap.delete("/app-connections/c1").mock(return_value=Response(204))

    await dienst.delete_connection("c1")

    assert verwijderen.called


@pytest.mark.asyncio
async def test_verwijderen_stuurt_geen_json_contenttype_zonder_body(
    dienst: ActivePiecesService, ap: Any
) -> None:
    """AP weigert een lege body met `Content-Type: application/json` met een 400 (gemeten)."""
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    verwijderen = ap.delete("/app-connections/c1").mock(return_value=Response(204))

    await dienst.delete_connection("c1")

    assert "content-type" not in verwijderen.calls.last.request.headers


@pytest.mark.asyncio
async def test_testen_leest_de_status_want_ap_heeft_geen_testroute(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    testroute = ap.post("/app-connections/c1/test").mock(return_value=Response(404))

    resultaat = await dienst.test_connection("c1")

    assert (resultaat["success"], testroute.called) == (True, False)


@pytest.mark.asyncio
async def test_een_verbinding_met_status_error_test_niet_als_gelukt(
    dienst: ActivePiecesService, ap: Any
) -> None:
    item = _item([EIGEN])
    item["status"] = "ERROR"
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=item))

    resultaat = await dienst.test_connection("c1")

    assert resultaat["success"] is False


@pytest.mark.asyncio
async def test_een_verbinding_gedeeld_met_een_ander_project_is_niet_van_deze_tenant(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN, VREEMD])))

    with pytest.raises(ApRessourceNietGevondenError):
        await dienst.get_connection("c1")


@pytest.mark.asyncio
async def test_een_nieuwe_sleutel_kan_het_verbindingstype_niet_overschrijven(
    dienst: ActivePiecesService, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=_item([EIGEN])))
    upsert = ap.post("/app-connections").mock(return_value=Response(201, json=_item([EIGEN])))

    await dienst.update_connection("c1", name=None, value={"type": "CUSTOM_AUTH", "x": "y"})

    assert json.loads(upsert.calls.last.request.content)["value"]["type"] == "NO_AUTH"


@pytest.mark.asyncio
async def test_een_nieuwe_sleutel_zonder_externalid_wordt_geweigerd_en_maakt_niets_aan(
    dienst: ActivePiecesService, ap: Any
) -> None:
    item = _item([EIGEN])
    del item["externalId"]
    ap.get("/app-connections/c1").mock(return_value=Response(200, json=item))
    upsert = ap.post("/app-connections").mock(return_value=Response(201, json=_item([EIGEN])))

    with pytest.raises(ValidatieFout):
        await dienst.update_connection("c1", name=None, value={"secret_text": "nieuw"})

    assert not upsert.called
