"""De client bouwt een flow met de versies van de server waar hij tegen praat.

Serverversie komt uit GET /v1/flags (vlag CURRENT_VERSION, aanwezig in 0.81.4 en 0.92.1:
packages/server/api/src/app/flags/flag.service.ts). Piece-versies uit GET /v1/pieces.
"""

import json
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.verbinding import ApVerbinding

BASE_URL = "http://activepieces:80/api/v1"
GRAPH = {
    "name": "Ref Flow",
    "nodes": [
        {"id": "classify", "agent_name": "openai", "config": {"prompt": "x"}},
        {"id": "notify", "agent_name": "slack", "config": {"text": "{{classify.category}}"}},
    ],
    "edges": [{"source": "classify", "target": "notify"}],
}
PIECES = [
    {"name": "@activepieces/piece-openai", "displayName": "OpenAI", "version": "0.7.3"},
    {"name": "@activepieces/piece-slack", "displayName": "Slack", "version": "0.11.2"},
]


@pytest.fixture
def client() -> ActivePiecesClient:
    ap_client = ActivePiecesClient(
        ApVerbinding(
            tenant_id=1,
            base_url=BASE_URL,
            email="test@example.com",
            wachtwoord="password",
            project_id="p1",
        )
    )
    ap_client.token = "valid-token"
    return ap_client


def _mock_server(respx_mock: respx.MockRouter, version: str) -> None:
    respx_mock.post("/authentication/sign-in").mock(
        return_value=Response(200, json={"token": "valid-token"})
    )
    respx_mock.get("/flags").mock(return_value=Response(200, json={"CURRENT_VERSION": version}))
    respx_mock.get("/pieces").mock(return_value=Response(200, json=PIECES))


@pytest.mark.asyncio
async def test_server_version_comes_from_flags(client: ActivePiecesClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        _mock_server(respx_mock, "0.81.4")
        assert await client.get_server_version() == "0.81.4"


@pytest.mark.asyncio
async def test_missing_version_flag_is_an_error(client: ActivePiecesClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        _mock_server(respx_mock, "0.81.4")
        respx_mock.get("/flags").mock(return_value=Response(200, json={}))
        with pytest.raises(ValueError, match="CURRENT_VERSION"):
            await client.get_server_version()


@pytest.mark.asyncio
async def test_build_pins_exact_versions_from_the_catalog(client: ActivePiecesClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        _mock_server(respx_mock, "0.81.4")
        flow = await client.build_flow_definition(GRAPH)
    assert flow["actions"]["classify"]["settings"]["pieceVersion"] == "0.7.3"


@pytest.mark.asyncio
async def test_build_on_0_81_keeps_bare_references(client: ActivePiecesClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        _mock_server(respx_mock, "0.81.4")
        flow = await client.build_flow_definition(GRAPH)
    assert flow["actions"]["notify"]["settings"]["input"]["text"] == "{{classify.category}}"


@pytest.mark.asyncio
async def test_build_on_0_92_wraps_references(client: ActivePiecesClient) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        _mock_server(respx_mock, "0.92.1")
        flow = await client.build_flow_definition(GRAPH)
    assert flow["actions"]["notify"]["settings"]["input"]["text"] == (
        "{{classify['output'].category}}"
    )


@pytest.mark.asyncio
async def test_execute_workflow_sends_the_versioned_flow(client: ActivePiecesClient) -> None:
    """Met een flow die de stappencontrole haalt (wfb-dag1 stap 1): GRAPH heeft openai en slack,
    en die worden sindsdien geweigerd (tests/unit/test_activepieces/test_client_weigert_...)."""
    graaf = {
        "name": "Ref Flow",
        "nodes": [{"id": "opmaak", "agent_name": "data_transformer", "config": {}}],
        "edges": [],
    }
    mapper = {"name": "@activepieces/piece-data-mapper", "displayName": "M", "version": "0.3.1"}
    in_ap = {"trigger": {"name": "trigger", "type": "EMPTY", "settings": {}}}
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False, assert_all_called=False) as respx_mock:
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "valid-token"})
        )
        respx_mock.get("/flags").mock(return_value=Response(200, json={"CURRENT_VERSION": "0.92.1"}))
        respx_mock.get("/pieces").mock(return_value=Response(200, json=[mapper]))
        respx_mock.get("/flows").mock(return_value=Response(200, json={"data": []}))
        create = respx_mock.post("/flows").mock(return_value=Response(200, json={"id": "f1"}))
        respx_mock.get("/flows/f1").mock(
            return_value=Response(200, json={"projectId": "p1", "version": in_ap})
        )
        respx_mock.post("/flows/f1/runs").mock(return_value=Response(200, json={"id": "r1"}))
        result = await client.execute_workflow(graaf, project_id="p1")
    assert result["success"] is True
    sent = json.loads(create.calls.last.request.content)
    assert sent["actions"]["opmaak"]["settings"]["pieceVersion"] == "0.3.1"
