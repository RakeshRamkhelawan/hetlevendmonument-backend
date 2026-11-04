"""Elke route die een flow opslaat, publiceert, aanzet of uitvoert weigert een uitgaande stap (wfb-dag1 stap 1).

Gemeten per ingang, met 422 en een Nederlandse melding, en telkens met de controle dat er NIETS
is gebeurd: geen schrijfactie bij ActivePieces en geen lokaal opgeslagen flow.

Ingangen (de volledige lijst staat in
tests/architecture/test_flow_ingangen_lopen_langs_de_stappencontrole.py):
- /api/v1/integrations/flows: POST, PUT, POST .../toggle, POST .../execute;
- /api/v1/workflows/execute;
- /api/v1/focus-builder/flows: in tests/integration/api/test_focus_builder_weigert_uitgaande_stappen.py
  (de tabel `flows` heeft JSONB en draait niet op SQLite).

Opstelling: echte routers, echte diensten en echte `ActivePiecesClient`; alleen HTTP naar AP
(respx), de ingelogde gebruiker, de rolcontrole (`permission_checker`, eigen tests in
tests/integration/api/test_workflow_publicatierecht_per_rol.py) en de Council bij
focus-builder-execute (eigen tests) zijn vervangen. Database: de SQLite-sessie van de unittests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.verbinding import ApVerbindingOntbreektError
from tests.unit.test_activepieces.test_client_ap092 import BASE_URL
from tests.unit.test_activepieces.test_client_ap092 import client as ap_client  # noqa: F401

VERBODEN = ["email", "slack", "http_request", "database_query", "mijn_eigen_script", "ap_gmail"]

PIECES = [
    {"name": n, "displayName": n, "version": "1.0.0"}
    for n in (
        "@activepieces/piece-gmail",
        "@activepieces/piece-slack",
        "@activepieces/piece-http",
        "@activepieces/piece-postgres",
        "@activepieces/piece-code",
        "@activepieces/piece-data-mapper",
        "@activepieces/piece-schedule",
    )
]


def _graaf(agent: str) -> dict[str, Any]:
    """Een graaf in de vorm die de builder stuurt, met een stap `stap1` van soort `agent`."""
    return {
        "nodes": [
            {
                "id": "stap1",
                "type": "action",
                "position": {"x": 0, "y": 0},
                "data": {"name": agent, "config": {}},
            },
        ],
        "edges": [],
    }


def _ap_flow(piece: str, actie: str) -> dict[str, Any]:
    return {
        "id": "flow-1",
        "projectId": "p1",
        "status": "DISABLED",
        "version": {
            "displayName": "Bestaand",
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
        },
    }


def _overschrijf_rolcontrole(app: FastAPI) -> None:
    async def _recht() -> int:
        return 1

    for route in app.routes:
        if isinstance(route, APIRoute):
            for afh in _alle(route.dependant):
                if getattr(afh, "__name__", "") == "permission_checker":
                    app.dependency_overrides[afh] = _recht


def _alle(dependant: Any) -> Iterator[Any]:
    for sub in dependant.dependencies:
        yield sub.call
        yield from _alle(sub)


@pytest.fixture
def ap() -> Iterator[Any]:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        mock.post("/authentication/sign-in").mock(return_value=Response(200, json={"token": "t"}))
        mock.get("/flags").mock(return_value=Response(200, json={"CURRENT_VERSION": "0.81.4"}))
        mock.get("/pieces").mock(return_value=Response(200, json=PIECES))
        mock.get("/projects").mock(return_value=Response(200, json={"data": [{"id": "p1"}]}))
        mock.get("/flows").mock(return_value=Response(200, json={"data": []}))
        yield mock


@pytest_asyncio.fixture
async def integraties(
    ap_client: ActivePiecesClient,  # noqa: F811
    ap: Any,
) -> AsyncGenerator[AsyncClient, None]:
    from src.core.activepieces.service import ActivePiecesService, get_activepieces_service
    from src.core.api.v1.activepieces.execution_router import router as uitvoer_router
    from src.core.api.v1.activepieces.flows_router import router as flow_router
    from src.core.auth.api_deps import get_current_user

    app = FastAPI()
    app.include_router(flow_router, prefix="/api/v1")
    app.include_router(uitvoer_router, prefix="/api/v1")
    app.dependency_overrides[get_activepieces_service] = lambda: ActivePiecesService(
        client=ap_client
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, tenant_id=1, email="beheer@test.example", roles=["admin"]
    )
    _overschrijf_rolcontrole(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.unit
@pytest.mark.asyncio
class TestIntegratieRoutes:
    @pytest.mark.parametrize("agent", VERBODEN)
    async def test_opslaan_met_een_verboden_stap_geeft_422(
        self, integraties: AsyncClient, ap: Any, agent: str
    ) -> None:
        schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))

        antwoord = await integraties.post(
            "/api/v1/integrations/flows",
            json={"name": "x", "project_id": "p1", "react_flow_data": _graaf(agent)},
        )

        assert (antwoord.status_code, schrijven.called) == (422, False), antwoord.text

    async def test_de_melding_is_nederlands_en_noemt_de_stap(
        self, integraties: AsyncClient
    ) -> None:
        antwoord = await integraties.post(
            "/api/v1/integrations/flows",
            json={"name": "x", "project_id": "p1", "react_flow_data": _graaf("email")},
        )

        assert "stap1" in antwoord.text and "niet toegestaan" in antwoord.text

    async def test_opslaan_met_alleen_opmaak_slaagt(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))

        antwoord = await integraties.post(
            "/api/v1/integrations/flows",
            json={"name": "x", "project_id": "p1", "react_flow_data": _graaf("data_transformer")},
        )

        assert antwoord.status_code == 201, antwoord.text

    async def test_wijzigen_naar_een_mailstap_geeft_422(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.get("/flows/flow-1").mock(
            return_value=Response(200, json=_ap_flow("@activepieces/piece-data-mapper", "map_data"))
        )
        schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

        antwoord = await integraties.put(
            "/api/v1/integrations/flows/flow-1", json={"react_flow_data": _graaf("email")}
        )

        assert (antwoord.status_code, schrijven.called) == (422, False), antwoord.text

    async def test_publiceren_via_wijzigen_van_een_flow_met_een_mailstap_geeft_422(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.get("/flows/flow-1").mock(
            return_value=Response(200, json=_ap_flow("@activepieces/piece-gmail", "send_email"))
        )
        schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

        antwoord = await integraties.put(
            "/api/v1/integrations/flows/flow-1", json={"status": "ENABLED"}
        )

        assert (antwoord.status_code, schrijven.called) == (422, False), antwoord.text

    async def test_aanzetten_van_een_flow_met_een_mailstap_geeft_422(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.get("/flows/flow-1").mock(
            return_value=Response(200, json=_ap_flow("@activepieces/piece-gmail", "send_email"))
        )
        schrijven = ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

        antwoord = await integraties.post("/api/v1/integrations/flows/flow-1/toggle")

        assert (antwoord.status_code, schrijven.called) == (422, False), antwoord.text

    async def test_aanzetten_van_een_flow_met_alleen_opmaak_slaagt(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.get("/flows/flow-1").mock(
            return_value=Response(200, json=_ap_flow("@activepieces/piece-data-mapper", "map_data"))
        )
        ap.post("/flows/flow-1").mock(return_value=Response(200, json={"id": "flow-1"}))

        antwoord = await integraties.post("/api/v1/integrations/flows/flow-1/toggle")

        assert antwoord.status_code == 200, antwoord.text

    async def test_uitvoeren_van_een_flow_met_een_mailstap_geeft_422(
        self, integraties: AsyncClient, ap: Any
    ) -> None:
        ap.get("/flows/flow-1").mock(
            return_value=Response(200, json=_ap_flow("@activepieces/piece-gmail", "send_email"))
        )
        starten = ap.post("/flows/flow-1/runs").mock(return_value=Response(201, json={"id": "r"}))

        antwoord = await integraties.post(
            "/api/v1/integrations/flows/flow-1/execute", json={"payload": {}}
        )

        assert (antwoord.status_code, starten.called) == (422, False), antwoord.text


@pytest_asyncio.fixture
async def workflows(
    ap: Any,
    ap_client: ActivePiecesClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient, None]:
    from src.core.api.v1.workflow.dependencies import get_db
    from src.core.api.v1.workflow.workflow_execution_ap_router import router as wf_router
    from src.core.auth.api_deps import get_current_user

    async def _geen_db() -> AsyncGenerator[None, None]:
        yield None  # de route gebruikt de sessie niet; de weigering valt ervoor

    app = FastAPI()
    app.include_router(wf_router)
    app.dependency_overrides[get_db] = _geen_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, tenant_id=1, email="beheer@test.example", roles=["admin"]
    )
    _overschrijf_rolcontrole(app)
    # De route maakt zelf een client; in de test is dat de ingelogde client met respx erachter.
    async def _client_van_de_tenant(tenant_id: int, db: object = None) -> ActivePiecesClient:
        return ap_client

    monkeypatch.setattr(
        "src.core.api.v1.workflow.workflow_execution_ap_router.ap_client_voor",
        _client_van_de_tenant,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workflows_execute_met_een_mailstap_geeft_422(
    workflows: AsyncClient, ap: Any
) -> None:
    schrijven = ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))
    body = {
        "name": "x",
        "nodes": [{"id": "stap1", "agent_name": "email"}],
        "edges": [],
    }

    antwoord = await workflows.post("/api/v1/workflows/execute", json=body)

    assert (antwoord.status_code, schrijven.called) == (422, False), antwoord.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workflows_execute_geeft_ook_422_als_pas_ap_de_flow_weigert(
    workflows: AsyncClient, ap: Any
) -> None:
    """Gate 2 MEDIUM-3: de voorcontrole slaagt, maar wat AP daarna heeft niet. Geen 200."""
    ap.post("/flows").mock(return_value=Response(201, json={"id": "flow-1"}))
    ap.get("/flows/flow-1").mock(
        return_value=Response(200, json=_ap_flow("@activepieces/piece-gmail", "send_email"))
    )
    starten = ap.post("/flows/flow-1/runs").mock(return_value=Response(201, json={"id": "r"}))
    body = {
        "name": "x",
        "project_id": "p1",
        "nodes": [{"id": "stap1", "agent_name": "data_transformer"}],
        "edges": [],
    }

    antwoord = await workflows.post("/api/v1/workflows/execute", json=body)

    assert (antwoord.status_code, starten.called) == (422, False), antwoord.text
    assert "niet toegestaan" in antwoord.text, antwoord.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_workflows_execute_weigert_ook_als_ap_niet_is_ingericht(
    workflows: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De voorcontrole hangt niet af van AP: zonder inloggegevens geen 200 met `success: False`."""

    async def _geen_ap(tenant_id: int, db: object = None) -> ActivePiecesClient:
        raise ApVerbindingOntbreektError("er is nog geen verbinding.")

    monkeypatch.setattr(
        "src.core.api.v1.workflow.workflow_execution_ap_router.ap_client_voor", _geen_ap
    )
    body = {"name": "x", "nodes": [{"id": "stap1", "agent_name": "email"}], "edges": []}

    antwoord = await workflows.post("/api/v1/workflows/execute", json=body)

    assert antwoord.status_code == 422, antwoord.text
