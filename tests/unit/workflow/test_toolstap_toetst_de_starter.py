"""Een toolstap mag niet meer dan de mens die de workflow startte (brief 2026-10-23).

De provider toetst VOOR de broker het recht van de starter. De rechtencontrole zelf (rollen uit de database) wordt
in `tests/integration/test_workflowstap_niet_meer_dan_de_starter.py` met echte rollen gemeten; hier staat het
gedrag van de provider en de engine rond die controle.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker import workflow_identiteit
from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.providers import ProductionToolBroker
from src.core.workflow.state_machine import WorkflowStateMachine

pytestmark = pytest.mark.asyncio


def _provider_met_broker() -> tuple[ProductionToolBroker, MagicMock]:
    broker = MagicMock()
    broker.execute_tool = AsyncMock(return_value={"tasks": []})
    provider = ProductionToolBroker()
    provider._dienst = broker
    return provider, broker


class TestDeProviderToetstDeStarter:
    async def test_een_starter_zonder_het_recht_geeft_een_mislukte_stap(self) -> None:
        provider, _ = _provider_met_broker()

        with patch.object(
            workflow_identiteit, "starter_heeft_toolrecht", AsyncMock(return_value=False)
        ):
            uitkomst = await provider.execute_tool("create_task", {}, tenant_id=5, starter="9")

        assert uitkomst["success"] is False

    async def test_een_starter_zonder_het_recht_raakt_de_broker_niet(self) -> None:
        provider, broker = _provider_met_broker()

        with patch.object(
            workflow_identiteit, "starter_heeft_toolrecht", AsyncMock(return_value=False)
        ):
            await provider.execute_tool("create_task", {}, tenant_id=5, starter="9")

        assert broker.execute_tool.await_count == 0

    async def test_de_weigering_zegt_in_gewone_taal_wie_de_workflow_startte(self) -> None:
        provider, _ = _provider_met_broker()

        with patch.object(
            workflow_identiteit, "starter_heeft_toolrecht", AsyncMock(return_value=False)
        ):
            uitkomst = await provider.execute_tool("create_task", {}, tenant_id=5, starter="9")

        assert "startte" in str(uitkomst["error"])

    async def test_een_starter_met_het_recht_laat_de_broker_draaien(self) -> None:
        provider, broker = _provider_met_broker()

        with patch.object(
            workflow_identiteit, "starter_heeft_toolrecht", AsyncMock(return_value=True)
        ):
            await provider.execute_tool("list_tasks", {}, tenant_id=5, starter="9")

        assert broker.execute_tool.await_count == 1

    async def test_zonder_starter_draait_er_geen_toolstap(self) -> None:
        provider, broker = _provider_met_broker()

        uitkomst = await provider.execute_tool("list_tasks", {}, tenant_id=5, starter=None)

        assert (uitkomst["success"], broker.execute_tool.await_count) == (False, 0)

    async def test_de_toets_krijgt_starter_toolnaam_en_klant_van_de_uitvoering(self) -> None:
        provider, _ = _provider_met_broker()
        toets = AsyncMock(return_value=True)

        with patch.object(workflow_identiteit, "starter_heeft_toolrecht", toets):
            await provider.execute_tool("update_task", {}, tenant_id=5, starter="9")

        toets.assert_awaited_once_with("9", "update_task", 5)


class TestDeStarterKomtVanDeUitvoering:
    async def test_de_engine_geeft_de_starter_aan_de_toolstap(self) -> None:
        tools = MagicMock()
        tools.execute_tool = AsyncMock(return_value={"success": True, "result": {}})
        motor = ProductionWorkflowEngine(
            db_session=MagicMock(),
            llm_provider=MagicMock(),
            tool_broker=tools,
            agent_runtime=MagicMock(),
            state_machine=WorkflowStateMachine(),
        )

        await motor._execute_tool_task({"tool_name": "list_tasks"}, {}, tenant_id=5, starter="9")

        assert tools.execute_tool.await_args is not None
        assert tools.execute_tool.await_args.kwargs["starter"] == "9"

    async def test_execute_task_neemt_de_starter_uit_de_uitvoering_zelf(self) -> None:
        """De weg van `initiated_by` op de uitvoering naar de toolstap, niet alleen de laatste schakel."""
        tools = MagicMock()
        tools.execute_tool = AsyncMock(return_value={"success": True, "result": {}})
        motor = ProductionWorkflowEngine(
            db_session=MagicMock(commit=AsyncMock()),
            llm_provider=MagicMock(),
            tool_broker=tools,
            agent_runtime=MagicMock(),
            state_machine=WorkflowStateMachine(),
        )
        uitvoering = SimpleNamespace(
            id="e1",
            tenant_id=5,
            initiated_by="9",
            input_json={},
            tasks_completed=0,
            workflow=SimpleNamespace(workflow_id="w1", version=1, spec_json={}),
        )
        motor._get_execution = AsyncMock(return_value=uitvoering)  # type: ignore[method-assign]
        motor._get_task = AsyncMock(return_value=SimpleNamespace(task_ref="t1"))  # type: ignore[method-assign]
        motor._get_completed_tasks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        motor._update_task_status = AsyncMock()  # type: ignore[method-assign]
        motor._parse_spec = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(
                tasks={"t1": {"type": "tool", "tool_name": "list_tasks", "parameters": {}}}
            )
        )

        await motor.execute_task("e1", "t1")

        assert tools.execute_tool.await_args is not None
        assert tools.execute_tool.await_args.kwargs["starter"] == "9"


class TestDeUitkomstVanEenToolstapIsOpslaanbaar:
    """Gemeten 2026-10-22 met een echte starter met schrijfrecht: `create_task` maakte de taak aan, maar de uitvoering
    eindigde op `failed` (`Object of type UUID is not JSON serializable` bij het opslaan van `result_json`)."""

    async def test_een_uitkomst_met_uuid_en_datum_wordt_als_json_opgeslagen(self) -> None:
        tools = MagicMock()
        tools.execute_tool = AsyncMock(
            return_value={
                "success": True,
                "result": {
                    "id": uuid.UUID(int=7),
                    "aangemaakt": datetime(2026, 10, 22, tzinfo=timezone.utc),
                },
            }
        )
        motor = ProductionWorkflowEngine(
            db_session=MagicMock(commit=AsyncMock()),
            llm_provider=MagicMock(),
            tool_broker=tools,
            agent_runtime=MagicMock(),
            state_machine=WorkflowStateMachine(),
        )
        taak = SimpleNamespace(task_ref="t1", result_json=None, finished_at=None)
        uitvoering = SimpleNamespace(
            id="e1",
            tenant_id=5,
            initiated_by="9",
            input_json={},
            tasks_completed=0,
            workflow=SimpleNamespace(workflow_id="w1", version=1, spec_json={}),
        )
        motor._get_execution = AsyncMock(return_value=uitvoering)  # type: ignore[method-assign]
        motor._get_task = AsyncMock(return_value=taak)  # type: ignore[method-assign]
        motor._get_completed_tasks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        motor._update_task_status = AsyncMock()  # type: ignore[method-assign]
        motor._parse_spec = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(
                tasks={"t1": {"type": "tool", "tool_name": "create_task", "parameters": {}}}
            )
        )

        resultaat = await motor.execute_task("e1", "t1")

        assert json.loads(json.dumps(taak.result_json))["result"]["id"] == str(uuid.UUID(int=7))
        # ook wat de volgende stap en de uitkomst van de hele uitvoering krijgen (`context[task_ref] = result.output`)
        assert json.loads(json.dumps(resultaat.output))["result"]["id"] == str(uuid.UUID(int=7))


class TestStarterWordtStreng:
    """Een starter die geen gebruikers-id is, bereikt de rechtencontrole niet eens."""

    @pytest.mark.parametrize("starter", [None, "", "  ", "systeem", "12abc", "-3", "0", "²", "٤"])
    async def test_geen_geldig_gebruikers_id_geen_vraag_aan_de_rechten(
        self, starter: str | None
    ) -> None:
        from src.core.auth import rbac

        vraag = AsyncMock(return_value=True)

        with patch.object(rbac.rbac_service, "user_has_tool_right", vraag):
            mag = await workflow_identiteit.starter_heeft_toolrecht(starter, "list_tasks", 5)

        assert (mag, vraag.await_count) == (False, 0)

    async def test_een_geldig_gebruikers_id_wordt_aan_de_rechten_voorgelegd(self) -> None:
        from src.core.auth import rbac

        vraag = AsyncMock(return_value=True)

        with patch.object(rbac.rbac_service, "user_has_tool_right", vraag):
            mag = await workflow_identiteit.starter_heeft_toolrecht("9", "list_tasks", 5)

        vraag.assert_awaited_once_with(9, "list_tasks", tenant_id=5)
        assert mag is True
