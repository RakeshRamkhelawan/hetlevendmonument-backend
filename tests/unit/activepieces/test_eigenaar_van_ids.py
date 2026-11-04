"""Een flow-, run- of verbindings-id van een ander project geeft 404 en raakt niets (ADR-040 B3).

Brief 2026-10-21 (ActivePieces per klant, dag 2), besluit 3.

**Wat er stond.** De client logt in met een serviceaccount dat bij ELK project kan. Een id uit het
pad (`/flows/{id}`, `/flow-runs/{id}`, `/connections/{id}`) ging ongecontroleerd door: een tenant
met het id van een flow van een andere klant kon die lezen, aanzetten, starten en verwijderen.

**Wat deze tests bewaken.** Elk id wordt bij ActivePieces opgevraagd en moet in het project van
DEZE tenant staan; anders 404, hetzelfde antwoord als voor een id dat niet bestaat, en er gaat
GEEN schrijfopdracht naar AP. Systeemgrens: alleen HTTP naar AP is vervangen (respx).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import respx
from httpx import Response

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.verbinding import ApRessourceNietGevondenError, ApVerbinding

BASE_URL = "http://ap.example.test/api/v1"
EIGEN = "proj-eigen"
VREEMD = "proj-vreemd"


@pytest.fixture
def client() -> ActivePiecesClient:
    ap_client = ActivePiecesClient(
        ApVerbinding(
            tenant_id=7,
            base_url=BASE_URL,
            email="ap@example.test",
            wachtwoord="geheim-voor-de-test",
            project_id=EIGEN,
        )
    )
    ap_client.token = "t"
    return ap_client


@pytest.fixture
def ap() -> Iterator[Any]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post("/authentication/sign-in").mock(return_value=Response(200, json={"token": "t"}))
        yield mock


def _flow(project: str | None, flow_id: str = "f1") -> dict[str, Any]:
    flow: dict[str, Any] = {"id": flow_id, "version": {"trigger": {"type": "EMPTY"}}}
    if project is not None:
        flow["projectId"] = project
    return flow


@pytest.mark.asyncio
async def test_een_eigen_flow_wordt_gegeven(client: ActivePiecesClient, ap: Any) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(EIGEN)))

    assert (await client.get_flow("f1"))["id"] == "f1"


@pytest.mark.asyncio
async def test_een_flow_van_een_ander_project_geeft_404(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(VREEMD)))

    with pytest.raises(ApRessourceNietGevondenError) as fout:
        await client.get_flow("f1")

    assert fout.value.status_code == 404


@pytest.mark.asyncio
async def test_een_flow_die_bij_ap_niet_bestaat_geeft_hetzelfde_404(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(404, json={"message": "weg"}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.get_flow("f1")


@pytest.mark.asyncio
async def test_een_antwoord_zonder_project_telt_als_niet_van_deze_tenant(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(None)))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.get_flow("f1")


@pytest.mark.asyncio
async def test_een_vreemde_flow_aanpassen_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(VREEMD)))
    schrijven = ap.post("/flows/f1").mock(return_value=Response(200, json={}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.update_flow("f1", {"type": "CHANGE_NAME", "request": {"displayName": "x"}})

    assert not schrijven.called


@pytest.mark.asyncio
async def test_een_vreemde_flow_verwijderen_geeft_404_en_geen_stille_false(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(VREEMD)))
    verwijderen = ap.delete("/flows/f1").mock(return_value=Response(200, json={}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.delete_flow("f1")

    assert not verwijderen.called


@pytest.mark.asyncio
async def test_een_vreemde_flow_starten_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(VREEMD)))
    starten = ap.post("/flows/f1/runs").mock(return_value=Response(201, json={"id": "r"}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.trigger_flow("f1", {})

    assert not starten.called


@pytest.mark.asyncio
async def test_de_runs_van_een_vreemde_flow_worden_niet_opgevraagd(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flows/f1").mock(return_value=Response(200, json=_flow(VREEMD)))
    lijst = ap.get("/flow-runs").mock(return_value=Response(200, json={"data": []}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.list_runs("f1")

    assert not lijst.called


@pytest.mark.asyncio
async def test_een_run_van_een_ander_project_geeft_404(client: ActivePiecesClient, ap: Any) -> None:
    ap.get("/flow-runs/r1").mock(
        return_value=Response(200, json={"id": "r1", "flowId": "f1", "projectId": VREEMD})
    )

    with pytest.raises(ApRessourceNietGevondenError):
        await client.get_run_logs("r1")


@pytest.mark.asyncio
async def test_een_vreemde_run_opnieuw_proberen_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flow-runs/r1").mock(
        return_value=Response(200, json={"id": "r1", "flowId": "f1", "projectId": VREEMD})
    )
    opnieuw = ap.post("/flow-runs/r1/retry").mock(return_value=Response(200, json={}))

    with pytest.raises(ApRessourceNietGevondenError):
        await client.retry_run("r1")

    assert not opnieuw.called


@pytest.mark.asyncio
async def test_een_vreemde_run_stoppen_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/flow-runs/r1").mock(return_value=Response(200, json={"id": "r1", "projectId": VREEMD}))
    stoppen = ap.post("/flow-runs/r1/stop").mock(return_value=Response(200, json={}))

    with pytest.raises(ApRessourceNietGevondenError):
        await ActivePiecesService(client=client).cancel_flow_run("r1")

    assert not stoppen.called


@pytest.mark.asyncio
async def test_een_vreemde_verbinding_geeft_404(client: ActivePiecesClient, ap: Any) -> None:
    ap.get("/app-connections/c1").mock(
        return_value=Response(200, json={"id": "c1", "projectIds": [VREEMD]})
    )

    with pytest.raises(ApRessourceNietGevondenError):
        await client.get_connection("c1")


@pytest.mark.asyncio
async def test_een_vreemde_verbinding_verwijderen_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(
        return_value=Response(200, json={"id": "c1", "projectIds": [VREEMD]})
    )
    verwijderen = ap.delete("/app-connections/c1").mock(return_value=Response(204))

    with pytest.raises(ApRessourceNietGevondenError):
        await ActivePiecesService(client=client).delete_connection("c1")

    assert not verwijderen.called


@pytest.mark.asyncio
async def test_een_vreemde_verbinding_testen_geeft_404_en_geen_mislukte_test(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(
        return_value=Response(200, json={"id": "c1", "projectIds": [VREEMD]})
    )

    with pytest.raises(ApRessourceNietGevondenError):
        await ActivePiecesService(client=client).test_connection("c1")


@pytest.mark.asyncio
async def test_een_vreemde_verbinding_wijzigen_stuurt_niets_naar_ap(
    client: ActivePiecesClient, ap: Any
) -> None:
    ap.get("/app-connections/c1").mock(
        return_value=Response(200, json={"id": "c1", "projectIds": [VREEMD]})
    )
    wijzigen = ap.post("/app-connections/c1").mock(return_value=Response(200, json={}))

    with pytest.raises(ApRessourceNietGevondenError):
        await ActivePiecesService(client=client).update_connection("c1", name="x")

    assert not wijzigen.called
