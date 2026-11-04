"""De uitgang naar ActivePieces laat geen flow met een uitgaande stap door (wfb-dag1 stap 1).

`ActivePiecesClient` is de enige plek die flows naar AP schrijft of start
(tests/architecture/test_flow_ingangen_lopen_langs_de_stappencontrole.py). Hier wordt gemeten dat
hij bij opslaan, aanzetten en uitvoeren de stappencontrole doet, en dat er bij een weigering NIETS
bij AP aankomt. Systeemgrens: alleen HTTP naar AP is vervangen (respx). De client-fixture komt uit
test_client_ap092.py (zelfde opstelling, al ingelogd).
"""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.stappencontrole import NietToegestaneStap
from tests.unit.test_activepieces.test_client_ap092 import BASE_URL
from tests.unit.test_activepieces.test_client_ap092 import client  # noqa: F401 - fixture


def _definitie(piece: str, actie: str) -> dict[str, Any]:
    return {
        "displayName": "Test",
        "trigger": {
            "name": "trigger",
            "type": "EMPTY",
            "settings": {},
            "nextAction": {
                "name": "stap1",
                "type": "PIECE",
                "settings": {"pieceName": piece, "actionName": actie},
            },
        },
    }


MAIL = _definitie("@activepieces/piece-gmail", "send_email")
OPMAAK = _definitie("@activepieces/piece-data-mapper", "map_data")


@pytest.fixture
def ap() -> Any:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post("/authentication/sign-in").mock(return_value=Response(200, json={"token": "t"}))
        yield mock


def _bestaande_flow(ap: Any, definitie: dict[str, Any]) -> None:
    ap.get("/flows/flow-1").mock(
        return_value=Response(
            200,
            json={
                "id": "flow-1",
                "projectId": "p1",
                "status": "DISABLED",
                "version": definitie,
            },
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aanmaken_met_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.create_flow("p1", MAIL)

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aanmaken_met_alleen_opmaak_bereikt_ap_wel(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))

    await client.create_flow("p1", OPMAAK)

    assert schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wijzigen_naar_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    _bestaande_flow(ap, OPMAAK)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", MAIL)

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aanzetten_van_een_flow_met_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    _bestaande_flow(ap, MAIL)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", {"status": "ENABLED"})

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uitzetten_mag_altijd(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """Andere kant op: een flow met een oude mailstap moet je wel kunnen UITzetten."""
    _bestaande_flow(ap, MAIL)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    await client.update_flow("flow-1", {"status": "DISABLED"})

    assert schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uitvoeren_van_een_flow_met_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    _bestaande_flow(ap, MAIL)
    starten = ap.post("/flows/flow-1/runs").mock(return_value=Response(201, json={"id": "run-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.trigger_flow("flow-1", {})

    assert not starten.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uitvoeren_van_een_flow_met_alleen_opmaak_mag(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    _bestaande_flow(ap, OPMAAK)
    starten = ap.post("/flows/flow-1/runs").mock(return_value=Response(201, json={"id": "run-1"}))

    await client.trigger_flow("flow-1", {})

    assert starten.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_lege_flow_aanmaken_met_alleen_een_naam_mag(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """Zo maakt AP zelf een flow aan; zonder stappen gaat er niets naar buiten."""
    schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))

    await client.create_flow("p1", {"displayName": "Leeg"})

    assert schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_flow_met_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """ADR-040 B7: opslaan via IMPORT_FLOW; de definitie staat dan onder `request`."""
    _bestaande_flow(ap, OPMAAK)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", {"type": "IMPORT_FLOW", "request": MAIL})

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opdracht",
    [
        {"type": "LOCK_AND_PUBLISH", "request": {}},
        {"type": "CHANGE_STATUS", "request": {"status": "ENABLED"}},
    ],
)
async def test_publiceren_of_aanzetten_via_een_operatie_controleert_de_flow(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
    opdracht: dict[str, Any],
) -> None:
    _bestaande_flow(ap, MAIL)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", opdracht)

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_onbekende_operatie_is_niet_te_controleren_en_wordt_geweigerd(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """Fail-closed: ADD_ACTION voegt een stap toe die nog niet in AP staat."""
    _bestaande_flow(ap, OPMAAK)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))
    stap = {"type": "PIECE", "settings": {"pieceName": "@activepieces/piece-gmail"}}

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", {"type": "ADD_ACTION", "request": {"action": stap}})

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_alleen_de_naam_wijzigen_mag(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    _bestaande_flow(ap, OPMAAK)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    await client.update_flow("flow-1", {"displayName": "Nieuwe naam", "description": "x"})

    assert schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_workflow_slikt_de_weigering_niet_in(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """`execute_workflow` vangt elke fout af tot `success: False`; deze weigering moet erdoor."""
    ap.get("/flags").mock(return_value=Response(200, json={"CURRENT_VERSION": "0.81.4"}))
    ap.get("/pieces").mock(
        return_value=Response(
            200,
            json=[{"name": "@activepieces/piece-gmail", "displayName": "G", "version": "1.0.0"}],
        )
    )
    ap.get("/flows").mock(return_value=Response(200, json={"data": []}))
    schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))
    graaf = {"name": "x", "nodes": [{"id": "m", "agent_name": "email"}], "edges": []}

    with pytest.raises(NietToegestaneStap):
        await client.execute_workflow(graaf)

    assert not schrijven.called


VEILIGE_TRIGGER = {"name": "trigger", "type": "EMPTY", "settings": {}}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opdracht",
    [
        # Gate 2 HIGH-2: een veilige trigger naast een operatie die een stap toevoegt.
        {"type": "ADD_ACTION", "trigger": VEILIGE_TRIGGER, "request": {"action": {"type": "PIECE"}}},
        # `request` zonder soort mag niet als "alleen gegevens" doorgaan.
        {"displayName": "x", "request": {"trigger": VEILIGE_TRIGGER}},
        # Een status buiten ENABLED/DISABLED (Gate 2 LOW-7).
        {"status": "enabled"},
        # IMPORT_FLOW met een tweede definitie ernaast.
        {"type": "IMPORT_FLOW", "version": {"trigger": VEILIGE_TRIGGER}, "request": MAIL},
    ],
)
async def test_een_gemengde_of_onbekende_opdracht_wordt_geweigerd(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
    opdracht: dict[str, Any],
) -> None:
    _bestaande_flow(ap, OPMAAK)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", opdracht)

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opdracht",
    [
        {"status": "ENABLED", "trigger": VEILIGE_TRIGGER},
        {"type": "LOCK_AND_PUBLISH", "request": {}},
    ],
)
async def test_aanzetten_met_een_veilige_trigger_erbij_controleert_toch_wat_ap_heeft(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
    opdracht: dict[str, Any],
) -> None:
    """Gate 2 HIGH-2: een meegestuurde veilige definitie mag de controle van AP niet vervangen."""
    _bestaande_flow(ap, MAIL)
    schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.update_flow("flow-1", opdracht)

    assert not schrijven.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opnieuw_proberen_van_een_run_van_een_flow_met_een_mailstap_bereikt_ap_niet(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    """Gate 2 HIGH-1: retry voert de flow opnieuw uit; de flow komt uit de run zelf."""
    ap.get("/flow-runs/run-1").mock(return_value=Response(200, json={"id": "run-1", "flowId": "flow-1", "projectId": "p1"}))
    _bestaande_flow(ap, MAIL)
    opnieuw = ap.post("/flow-runs/run-1/retry").mock(return_value=Response(200, json={"id": "run-1"}))

    with pytest.raises(NietToegestaneStap):
        await client.retry_run("run-1")

    assert not opnieuw.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_opnieuw_proberen_van_een_run_van_een_veilige_flow_mag(
    client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> None:
    ap.get("/flow-runs/run-1").mock(return_value=Response(200, json={"id": "run-1", "flowId": "flow-1", "projectId": "p1"}))
    _bestaande_flow(ap, OPMAAK)
    opnieuw = ap.post("/flow-runs/run-1/retry").mock(return_value=Response(200, json={"id": "run-1"}))

    await client.retry_run("run-1")

    assert opnieuw.called
