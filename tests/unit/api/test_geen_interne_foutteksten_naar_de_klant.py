"""Een vreemde fout met een intern adres erin komt nooit in het antwoord naar de klant.

Brief 2026-10-21 (geen interne foutteksten naar de klant). De security-review vond zeven plekken
waar `str(e)` van een httpx-, database- of taalmodelfout in een antwoord belandde. Elke test hier
laat die plek een fout krijgen waarvan de tekst een herkenbaar INTERN adres bevat, en meet het
ANTWOORD: een `HTTPException.detail`, een JSON-veld of een websocketbericht.

De guard `tests/architecture/test_geen_uitzonderingstekst_in_een_antwoord.py` sluit de soort; deze
tests bewijzen dat de zeven genoemde plekken echt dicht zijn en dat het antwoord nog steeds de
vorm heeft die de aanroeper verwacht (een fout is een fout, geen 200 met een lege body).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from tests.unit.api.test_focus_builder_ws_chat import app_with_overrides  # noqa: F401

INTERN = "http://ap-intern.example:8080/api/v1/pieces"
LEK = "ap-intern.example"
FOUT = f"All connection attempts failed for url '{INTERN}'"


def _endpoint(router: APIRouter, pad_eindigt_op: str, methode: str) -> Any:
    """De oorspronkelijke routefunctie, zonder limiter- of rechtendecorators."""
    for route in router.routes:
        if getattr(route, "path", "").endswith(pad_eindigt_op) and methode in getattr(
            route, "methods", set()
        ):
            return inspect.unwrap(getattr(route, "endpoint"))
    raise AssertionError(f"geen {methode}-route die eindigt op {pad_eindigt_op}")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_piecesync_zet_geen_adres_in_de_fout() -> None:
    from src.core.api.v1.focus_builder.pieces_router import pieces_router

    sync = _endpoint(pieces_router, "/pieces/sync", "POST")
    dienst = MagicMock()
    dienst.sync_pieces_catalog = AsyncMock(side_effect=Exception(FOUT))

    with pytest.raises(HTTPException) as fout:
        await sync(
            request=MagicMock(),
            response=MagicMock(),
            service=dienst,
            current_user=SimpleNamespace(id=1),
            _=1,
        )

    assert LEK not in repr(fout.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_piecesync_blijft_een_500_geven() -> None:
    from src.core.api.v1.focus_builder.pieces_router import pieces_router

    sync = _endpoint(pieces_router, "/pieces/sync", "POST")
    dienst = MagicMock()
    dienst.sync_pieces_catalog = AsyncMock(side_effect=Exception(FOUT))

    with pytest.raises(HTTPException) as fout:
        await sync(
            request=MagicMock(),
            response=MagicMock(),
            service=dienst,
            current_user=SimpleNamespace(id=1),
            _=1,
        )

    assert fout.value.status_code == 500


@pytest.mark.unit
def test_de_websocket_stuurt_geen_adres_bij_een_mislukte_uitvoering(
    app_with_overrides: Any,  # noqa: F811
) -> None:
    router = "src.core.api.v1.focus_builder.ws_chat_router"
    gebruiker = MagicMock(id=1, tenant_id=1)
    dienst = MagicMock()
    dienst.execute_flow = AsyncMock(side_effect=Exception(FOUT))
    with (
        patch(f"{router}.validate_ws_token", new=AsyncMock(return_value=gebruiker)),
        patch(f"{router}.mag_flows_publiceren", new=AsyncMock(return_value=True)),
        patch(f"{router}.FocusBuilderToolAgent") as tool_agent,
        patch(f"{router}.FocusBuilderChatAgent") as chat_agent,
        patch("src.domains.flows.service.FocusBuilderService", return_value=dienst),
    ):
        tool_agent.return_value.start_session = AsyncMock()
        chat_agent.return_value.start_session = AsyncMock()
        with TestClient(app_with_overrides) as client:
            client.cookies.set("access_token", "test.jwt.token")
            with client.websocket_connect("/api/v1/focus-builder/ws/chat") as ws:
                ws.send_json({"type": "execute", "flow_id": 7})
                antwoord = ws.receive_json()

    assert LEK not in repr(antwoord) and antwoord.get("type") == "exec_error", antwoord


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_health_van_de_proxy_noemt_het_adres_niet() -> None:
    from src.core.api.v1.focus_builder.proxy import create_proxy_router

    health = _endpoint(create_proxy_router(), "/health", "GET")
    client = MagicMock()
    client.get = AsyncMock(side_effect=Exception(FOUT))

    with patch(
        "src.core.api.v1.focus_builder.proxy.get_http_client", new=AsyncMock(return_value=client)
    ):
        antwoord = await health(request=MagicMock())

    assert LEK not in antwoord.body.decode() and antwoord.status_code == 503


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_flow_aanmaken_zet_geen_adres_in_de_fout() -> None:
    from src.core.api.v1.activepieces.flows_router import FlowCreateRequest, router

    maak = _endpoint(router, "/flows", "POST")
    dienst = MagicMock()
    dienst.create_flow = AsyncMock(side_effect=ValueError(FOUT))
    verzoek = FlowCreateRequest(
        name="x",
        description=None,
        project_id=None,
        react_flow_data={"nodes": [], "edges": []},
    )

    with pytest.raises(HTTPException) as fout:
        await maak(
            request=verzoek,
            http_request=MagicMock(),
            service=dienst,
            _current_user=SimpleNamespace(id=1),
            _publiceren=1,
        )

    assert LEK not in repr(fout.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_verbinding_aanmaken_zet_geen_adres_in_de_fout() -> None:
    from src.core.activepieces.schemas import ConnectionCreate
    from src.core.api.v1.activepieces.connections_router import router

    maak = _endpoint(router, "/connections", "POST")
    dienst = MagicMock()
    dienst.create_connection = AsyncMock(side_effect=ValueError(FOUT))
    verzoek = ConnectionCreate(name="n", app_name="slack", project_id=None, value={"token": "x"})

    with pytest.raises(HTTPException) as fout:
        await maak(
            request=verzoek,
            http_request=MagicMock(),
            service=dienst,
            _current_user=SimpleNamespace(id=1),
        )

    assert LEK not in repr(fout.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_workflowgeneratie_die_faalt_zet_geen_adres_in_de_fout() -> None:
    from src.core.api.v1.workflow.workflow_generation_router import router

    genereer = _endpoint(router, "/generate", "POST")
    verzoek = SimpleNamespace(prompt="x", complexity="simple")

    with patch(
        "src.core.api.v1.workflow.workflow_generation_router.create_workflow_generator",
        new=AsyncMock(side_effect=Exception(FOUT)),
    ):
        antwoord = await genereer(request=verzoek, current_user=SimpleNamespace(tenant_id=1))

    assert LEK not in antwoord.model_dump_json() and antwoord.success is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_verfijning_die_faalt_zet_geen_adres_in_bericht_of_fouten() -> None:
    from src.core.api.v1.workflow.workflow_refinement_router import router

    verfijn = _endpoint(router, "/refine", "POST")
    verzoek = SimpleNamespace(
        refinement=SimpleNamespace(type="x", title="t"),
        workflow=SimpleNamespace(nodes=[]),
    )

    with patch(
        "src.core.api.v1.workflow.workflow_refinement_router.WorkflowOrchestratorAgent",
        side_effect=Exception(FOUT),
    ):
        antwoord = await verfijn(
            request=verzoek,
            db=MagicMock(),
            current_user=SimpleNamespace(id=1),
            tenant_id=1,
            _=1,
        )

    assert LEK not in antwoord.model_dump_json() and antwoord.success is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_databasecontrole_zet_geen_adres_in_bericht_of_details() -> None:
    from src.core.monitoring.health_checks import HealthChecker

    manager = MagicMock()
    manager.get_session = MagicMock(side_effect=Exception(FOUT))

    with patch("src.core.database.database.db_manager", manager):
        resultaat = await HealthChecker().check_database()

    assert LEK not in repr((resultaat.message, resultaat.details))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_monitoringcontrole_zet_geen_adres_in_bericht_of_details() -> None:
    from src.core.monitoring.health_checks import HealthChecker

    with patch(
        "src.core.monitoring.advanced_analytics.get_metrics_collector",
        side_effect=Exception(FOUT),
    ):
        resultaat = await HealthChecker().check_monitoring()

    assert LEK not in repr((resultaat.message, resultaat.details))


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", ["uitzondering", "providerfout"])
async def test_een_flowgeneratie_die_faalt_zet_geen_adres_in_het_antwoord(pad: str) -> None:
    from src.domains.flows.agentic_service import AgenticFlowService

    llm = MagicMock()
    if pad == "uitzondering":
        llm.complete_json = AsyncMock(side_effect=Exception(FOUT))
    else:
        llm.complete_json = AsyncMock(
            return_value=SimpleNamespace(success=False, error_message=FOUT, content=None)
        )

    antwoord = await AgenticFlowService(llm_service=llm).generate_flow_from_prompt("x")

    assert LEK not in repr(antwoord) and antwoord["success"] is False
