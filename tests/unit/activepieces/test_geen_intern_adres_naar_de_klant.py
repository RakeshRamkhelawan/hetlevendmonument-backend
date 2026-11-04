"""Een fout met het interne AP-adres erin komt nooit bij de klant, en niet volledig in het log.

Gate 2 dag 2, gerichte review 2026-10-21: het health-pad was gerepareerd, maar `str(e)` van een
httpx-fout (die het hele adres noemt, `... for url 'http://ap-intern.example:8080/...'`) ging nog
naar de klant via `/workflows/execute`, de statusroute, `ActivePiecesClient.execute_workflow`,
`ActivePiecesService.test_connection` en `ActivePiecesService.execute_workflow`.

Naar buiten gaat een vaste Nederlandse tekst; het soort fout en de details alleen in het log, en
dan zonder het volledige adres (alleen de host).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from loguru import logger

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.verbinding import ApVerbinding

INTERN = "http://ap-intern.example:8080/api/v1"
LEK = "ap-intern.example"
FOUT = "All connection attempts failed for url '" + INTERN + "/pieces'"


def _client() -> ActivePiecesClient:
    client = ActivePiecesClient(
        ApVerbinding(
            tenant_id=1,
            base_url=INTERN,
            email="ap@example.test",
            wachtwoord="geheim-voor-de-test",
            project_id="proj-1",
        )
    )
    client.token = "t"
    return client


@pytest.fixture
def log() -> Iterator[list[str]]:
    regels: list[str] = []
    # De extra velden (`error=...`) staan niet in de tekstopmaak van loguru: ze erbij nemen, anders
    # ziet deze test precies het deel van het log niet waar het adres in staat.
    sink_id = logger.add(
        lambda bericht: regels.append(str(bericht) + repr(bericht.record["extra"])), level="DEBUG"
    )
    try:
        yield regels
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_execute_workflow_van_de_client_geeft_een_vaste_tekst_bij_een_fout() -> None:
    client = _client()

    with patch.object(client, "build_flow_definition", new=AsyncMock(side_effect=Exception(FOUT))):
        resultaat = await client.execute_workflow({"name": "x", "nodes": [], "edges": []})

    assert LEK not in repr(resultaat)


@pytest.mark.asyncio
async def test_execute_workflow_van_de_client_blijft_success_false_bij_een_fout() -> None:
    client = _client()

    with patch.object(client, "build_flow_definition", new=AsyncMock(side_effect=Exception(FOUT))):
        resultaat = await client.execute_workflow({"name": "x", "nodes": [], "edges": []})

    assert resultaat["success"] is False


@pytest.mark.asyncio
async def test_de_execute_route_zet_geen_adres_in_message_of_error() -> None:
    from src.core.api.v1.workflow.workflow_execution_ap_router import (
        WorkflowExecuteRequest,
        execute_workflow,
    )

    client = MagicMock()
    client.execute_workflow = AsyncMock(side_effect=Exception(FOUT))
    verzoek = WorkflowExecuteRequest.model_validate(
        {"name": "x", "nodes": [{"id": "n1", "agent_name": "data_transformer"}], "edges": []}
    )

    with patch(
        "src.core.api.v1.workflow.workflow_execution_ap_router.ap_client_voor",
        new=AsyncMock(return_value=client),
    ):
        antwoord = await execute_workflow(
            request=verzoek,
            current_user=SimpleNamespace(tenant_id=1),  # type: ignore[arg-type]
            db=MagicMock(),
            _publiceren=1,
        )

    assert LEK not in antwoord.model_dump_json()


@pytest.mark.asyncio
async def test_de_execute_route_geeft_geen_adres_door_uit_een_mislukte_client_uitkomst() -> None:
    from src.core.api.v1.workflow.workflow_execution_ap_router import (
        WorkflowExecuteRequest,
        execute_workflow,
    )

    client = MagicMock()
    client.execute_workflow = AsyncMock(return_value={"success": False, "error": FOUT})
    verzoek = WorkflowExecuteRequest.model_validate(
        {"name": "x", "nodes": [{"id": "n1", "agent_name": "data_transformer"}], "edges": []}
    )

    with patch(
        "src.core.api.v1.workflow.workflow_execution_ap_router.ap_client_voor",
        new=AsyncMock(return_value=client),
    ):
        antwoord = await execute_workflow(
            request=verzoek,
            current_user=SimpleNamespace(tenant_id=1),  # type: ignore[arg-type]
            db=MagicMock(),
            _publiceren=1,
        )

    assert LEK not in antwoord.model_dump_json()


@pytest.mark.asyncio
async def test_de_statusroute_zet_geen_adres_in_de_fout() -> None:
    from src.core.api.v1.workflow.workflow_execution_ap_router import get_execution_status

    client = MagicMock()
    client.get_run_logs = AsyncMock(side_effect=Exception(FOUT))

    antwoord = await get_execution_status(run_id="r1", ap_client=client)

    assert LEK not in antwoord.model_dump_json()


@pytest.mark.asyncio
async def test_een_verbindingstest_die_faalt_geeft_geen_adres_in_de_details() -> None:
    client = MagicMock()
    client.get_connection = AsyncMock(return_value={"projectId": "proj-1"})
    client._make_request = AsyncMock(side_effect=Exception(FOUT))

    resultaat = await ActivePiecesService(client=client).test_connection("c1")

    assert LEK not in repr(resultaat)


@pytest.mark.asyncio
async def test_de_service_execute_workflow_geeft_geen_adres_bij_een_fout() -> None:
    client = MagicMock()
    client.is_available = MagicMock(return_value=True)
    client.eigen_project = MagicMock(return_value="proj-1")
    client.build_flow_definition = AsyncMock(side_effect=Exception(FOUT))

    resultaat = await ActivePiecesService(client=client).execute_workflow(
        {"name": "x", "nodes": [], "edges": []}, tenant_id=1
    )

    assert LEK not in repr(resultaat)


@pytest.mark.asyncio
async def test_het_log_van_een_onbereikbare_ap_noemt_het_volledige_adres_niet(
    log: list[str],
) -> None:
    client = _client()
    client.token = None

    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{INTERN}/authentication/sign-in").mock(side_effect=httpx.ConnectError(FOUT))
        with pytest.raises(Exception):
            await client._authenticate()

    assert "/pieces" not in "".join(log) and "/authentication" not in "".join(log)


@pytest.mark.asyncio
async def test_het_log_van_een_mislukt_verzoek_noemt_het_volledige_adres_niet(
    log: list[str],
) -> None:
    client = _client()

    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{INTERN}/authentication/sign-in").mock(
            return_value=httpx.Response(200, json={"token": "t"})
        )
        mock.get(f"{INTERN}/pieces").mock(side_effect=httpx.ConnectError(FOUT))
        with pytest.raises(httpx.ConnectError):
            await client.list_pieces()

    assert "/pieces" not in "".join(log)


@pytest.mark.parametrize("poort", ["99999", "abc", "-1", "0x50"])
def test_een_ongeldige_poort_is_een_ongeldig_adres_en_geen_valueerror(poort: str) -> None:
    from src.core.activepieces.verbinding_beheer import OngeldigApAdres, controleer_adres

    with pytest.raises(OngeldigApAdres):
        controleer_adres(f"https://ap.example.com:{poort}/api/v1")
