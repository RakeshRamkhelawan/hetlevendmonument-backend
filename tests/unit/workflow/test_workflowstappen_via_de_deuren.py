"""Een taalmodelstap gaat via de deur van de klant, een toolstap via de echte broker (ADR-036 OP-13, brief 2026-10-22).

**Wat er mis was (gemeten 2026-10-22 met een echte worker).**
- Elke taalmodelstap faalde met `Can't instantiate abstract class BaseAgent`: `ProductionLLMProvider` bouwde een
  abstracte klasse. Bovendien kende hij de klant van de uitvoering niet, dus ook met een werkende klasse had de
  modelkeuze van de klant niet gegolden.
- Een toolstap importeerde een `ToolBrokerClient` die niet bestaat en gaf `success: False`, waarna de uitvoering toch
  op `succeeded` eindigde: een uitvoering die liegt.

**Wat hier bewezen wordt.**
1. De provider vraagt zijn model aan `TenantTaalmodel(tenant_id)` met de klant die de ENGINE meegeeft (de klant van de
   uitvoering); zonder klant geen antwoord (geen stille platformstandaard); geen `BaseAgent` meer.
2. De provider roept `ToolBrokerService.execute_tool` aan met de klant in de context en de identiteit
   `workflow_engine`, die een permissieprofiel heeft (default-deny, bewust klein).
3. Een weigering of een fout van de broker is een MISLUKTE stap met een Nederlandse reden; de engine laat een toolstap
   met `success: False` falen in plaats van door te gaan.

**Mutatiebewijs:** zie de oplevering van de brief (per element, beide richtingen).
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker import workflow_identiteit
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.workflow import providers
from src.core.workflow.engine import ProductionWorkflowEngine, StapMislukt
from src.core.workflow.providers import ProductionLLMProvider, ProductionToolBroker
from src.core.workflow.state_machine import WorkflowStateMachine


class _NepDeur:
    """Een `TenantTaalmodel` die onthoudt voor welke klant hij is gevraagd."""

    gevraagd_voor: list[int | None] = []
    laatste_systeem: str | None = None

    def __init__(self, tenant_id: int | None) -> None:
        self.tenant_id = tenant_id
        _NepDeur.gevraagd_voor.append(tenant_id)
        self.model_label = "mistral:klein"

    async def tekst_met_gebruik(
        self,
        prompt: str,
        *,
        systeem: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        _NepDeur.laatste_systeem = systeem
        return f"antwoord op {prompt}", 3, 4


class TestTaalmodelstap:
    def setup_method(self) -> None:
        _NepDeur.gevraagd_voor = []

    async def test_de_provider_vraagt_de_deur_van_de_klant(self) -> None:
        with patch.object(providers, "TenantTaalmodel", _NepDeur):
            await ProductionLLMProvider().generate("hallo", "genegeerd", tenant_id=7)

        assert _NepDeur.gevraagd_voor == [7]

    async def test_de_systeemprompt_van_de_stap_bereikt_het_model(self) -> None:
        with patch.object(providers, "TenantTaalmodel", _NepDeur):
            await ProductionLLMProvider().generate(
                "hallo", "genegeerd", system_prompt="Wees kort.", tenant_id=7
            )

        assert _NepDeur.laatste_systeem == "Wees kort."

    async def test_het_antwoord_heeft_de_vorm_die_de_engine_leest(self) -> None:
        with patch.object(providers, "TenantTaalmodel", _NepDeur):
            antwoord = await ProductionLLMProvider().generate("hallo", "genegeerd", tenant_id=7)

        assert antwoord == {
            "content": "antwoord op hallo",
            "provider": "mistral",
            "model": "mistral:klein",
            "tokens": 7,
            "finish_reason": "stop",
        }

    async def test_zonder_klant_komt_er_geen_antwoord(self) -> None:
        with patch.object(providers, "TenantTaalmodel", _NepDeur):
            with pytest.raises(ValueError, match="klant"):
                await ProductionLLMProvider().generate("hallo", "genegeerd")

        assert _NepDeur.gevraagd_voor == []

    async def test_een_storing_van_het_model_komt_als_uitzondering_bij_de_engine(self) -> None:
        class _Kapot(_NepDeur):
            async def tekst_met_gebruik(self, prompt: str, **_: Any) -> tuple[str, int, int]:
                raise ConnectionError("model onbereikbaar")

        with patch.object(providers, "TenantTaalmodel", _Kapot):
            with pytest.raises(ConnectionError, match="onbereikbaar"):
                await ProductionLLMProvider().generate("hallo", "genegeerd", tenant_id=7)

    def test_de_provider_gebruikt_geen_baseagent_meer(self) -> None:
        bron = inspect.getsource(ProductionLLMProvider)

        assert (
            "agents.base_agent" in bron,
            "base_agent_class" in bron,
            "process_task" in bron,
        ) == (
            False,
            False,
            False,
        )


def _motor(llm: Any = None, tools: Any = None) -> ProductionWorkflowEngine:
    return ProductionWorkflowEngine(
        db_session=MagicMock(),
        llm_provider=llm or MagicMock(),
        tool_broker=tools or MagicMock(),
        agent_runtime=MagicMock(),
        state_machine=WorkflowStateMachine(),
    )


class TestDeEngineGeeftDeKlantDoor:
    async def test_de_taalmodelstap_krijgt_de_klant_van_de_uitvoering(self) -> None:
        llm = MagicMock()
        llm.generate = AsyncMock(return_value={"content": "x"})

        await _motor(llm=llm)._execute_llm_task({"prompt": "hoi"}, {}, tenant_id=5)

        assert llm.generate.await_args.kwargs["tenant_id"] == 5

    async def test_de_toolstap_krijgt_de_klant_van_de_uitvoering(self) -> None:
        tools = MagicMock()
        tools.execute_tool = AsyncMock(return_value={"success": True, "result": {"a": 1}})

        await _motor(tools=tools)._execute_tool_task(
            {"tool_name": "list_tasks", "parameters": {}}, {}, tenant_id=5
        )

        assert tools.execute_tool.await_args.kwargs["tenant_id"] == 5


class TestToolstapLiegtNiet:
    async def test_een_toolstap_met_success_false_is_een_mislukte_stap(self) -> None:
        tools = MagicMock()
        tools.execute_tool = AsyncMock(
            return_value={"success": False, "result": None, "error": "geen toestemming"}
        )

        with pytest.raises(StapMislukt, match="geen toestemming"):
            await _motor(tools=tools)._execute_tool_task({"tool_name": "x"}, {}, tenant_id=5)

    async def test_een_toolstap_die_slaagt_geeft_zijn_uitvoer(self) -> None:
        tools = MagicMock()
        tools.execute_tool = AsyncMock(return_value={"success": True, "result": {"n": 2}})

        uitvoer = await _motor(tools=tools)._execute_tool_task({"tool_name": "x"}, {}, tenant_id=5)

        assert uitvoer["success"] is True


class TestAgentstapLiegtNiet:
    """Een agentstap die meldt dat hij mislukte, mislukt: de uitvoering eindigt niet op `succeeded`.

    Gemeten 2026-10-22 met de definitie die de builder bewaart: `{"success": false, "output": {"error": "Agent ... not
    found in process"}}` en toch `succeeded` (dezelfde leugen als bij de toolstap).
    """

    @staticmethod
    def _runtime(resultaat: dict[str, Any]) -> Any:
        runtime = MagicMock()
        runtime.run_agentstap = AsyncMock(return_value=resultaat)
        return runtime

    async def test_een_agentstap_met_success_false_is_een_mislukte_stap(self) -> None:
        motor = _motor()
        motor.agent_runtime = self._runtime(
            {"success": False, "output": {"error": "Agent x not found in process"}, "agent_id": "x"}
        )

        with pytest.raises(StapMislukt, match="not found in process"):
            await motor._execute_agent_task({"agent_id": "x"}, {}, tenant_id=5)

    async def test_een_agentstap_die_slaagt_geeft_zijn_uitvoer(self) -> None:
        motor = _motor()
        motor.agent_runtime = self._runtime({"success": True, "output": {"tekst": "hoi"}})

        uitvoer = await motor._execute_agent_task({"agent_id": "x"}, {}, tenant_id=5)

        assert uitvoer["output"] == {"tekst": "hoi"}

    async def test_een_agentstap_zonder_success_sleutel_blijft_gewoon_slagen(self) -> None:
        motor = _motor()
        motor.agent_runtime = self._runtime({"output": {"tekst": "hoi"}})

        uitvoer = await motor._execute_agent_task({"agent_id": "x"}, {}, tenant_id=5)

        assert uitvoer == {"output": {"tekst": "hoi"}}


class TestAgentstapKrijgtDeKlantVanDeUitvoering:
    """Gate 2 ronde 1, HIGH-1: `input_data` is van de beller en mag de klant van een agentstap niet kiezen.

    `AutonomousAgent.process_task` leest `task.metadata["tenant_id"]`; de context van een stap is `input_json` plus
    eerdere uitkomsten, dus een sleutel `tenant_id` in de invoer kwam daar ongehinderd.
    """

    async def test_een_tenant_id_in_de_context_wordt_overschreven_door_de_klant_van_de_uitvoering(
        self,
    ) -> None:
        motor = _motor()
        runtime = MagicMock()
        runtime.run_agentstap = AsyncMock(return_value={"success": True, "output": {}})
        motor.agent_runtime = runtime

        await motor._execute_agent_task({"agent_id": "x"}, {"tenant_id": 2}, tenant_id=5)

        assert runtime.run_agentstap.await_args.kwargs["context"]["tenant_id"] == 5

    async def test_zonder_tenant_id_in_de_context_krijgt_de_agent_toch_de_klant(self) -> None:
        motor = _motor()
        runtime = MagicMock()
        runtime.run_agentstap = AsyncMock(return_value={"success": True, "output": {}})
        motor.agent_runtime = runtime

        await motor._execute_agent_task({"agent_id": "x"}, {"naam": "a"}, tenant_id=5)

        assert runtime.run_agentstap.await_args.kwargs["context"] == {"naam": "a", "tenant_id": 5}

    async def test_de_starter_van_de_uitvoering_gaat_mee_naar_de_agent(self) -> None:
        motor = _motor()
        runtime = MagicMock()
        runtime.run_agentstap = AsyncMock(return_value={"success": True, "output": {}})
        motor.agent_runtime = runtime

        await motor._execute_agent_task({"agent_id": "x"}, {}, tenant_id=5, starter="42")

        assert runtime.run_agentstap.await_args.kwargs["starter"] == "42"


def _broker_met(
    resultaat: dict[str, object] | None = None, fout: Exception | None = None
) -> tuple[ProductionToolBroker, MagicMock]:
    dienst = MagicMock()
    dienst.execute_tool = AsyncMock(return_value=resultaat, side_effect=fout)
    broker = ProductionToolBroker()
    broker._dienst = dienst  # type: ignore[attr-defined]
    return broker, dienst


class TestToolBrokerProvider:
    """De starter-toets zelf staat in `test_toolstap_toetst_de_starter.py` en, met echte rollen, in
    `tests/integration/test_workflowstap_niet_meer_dan_de_starter.py`. Hier meten we alleen wat de provider aan de
    broker meegeeft; daarom laat deze fixture de toets slagen."""

    @pytest.fixture(autouse=True)
    def _starter_mag(self) -> Iterator[None]:
        with patch.object(
            workflow_identiteit, "starter_heeft_toolrecht", AsyncMock(return_value=True)
        ):
            yield

    async def test_de_provider_roept_de_echte_broker_aan_met_klant_en_identiteit(self) -> None:
        broker, dienst = _broker_met({"ok": True})

        await broker.execute_tool("list_tasks", {"a": 1}, tenant_id=7)

        aanroep = dienst.execute_tool.await_args.kwargs
        assert (aanroep["tool_name"], aanroep["agent_id"], aanroep["context"]) == (
            "list_tasks",
            "workflow_engine",
            {"tenant_id": 7},
        )

    async def test_een_geslaagde_aanroep_geeft_success_true_met_het_resultaat(self) -> None:
        broker, _ = _broker_met({"ok": True})

        uitkomst = await broker.execute_tool("list_tasks", {}, tenant_id=7)

        assert (uitkomst["success"], uitkomst["result"], uitkomst["error"]) == (
            True,
            {"ok": True},
            None,
        )

    async def test_een_weigering_wordt_success_false_met_een_nederlandse_reden(self) -> None:
        broker, _ = _broker_met(
            fout=ToolExecutionException(tool_name="x", error_detail="Permission denied")
        )

        uitkomst = await broker.execute_tool("x", {}, tenant_id=7)

        assert (uitkomst["success"], "tool" in uitkomst["error"].lower()) == (False, True)

    async def test_zonder_klant_geen_uitvoering(self) -> None:
        broker, dienst = _broker_met({"ok": True})

        uitkomst = await broker.execute_tool("list_tasks", {})

        assert (uitkomst["success"], dienst.execute_tool.await_count) == (False, 0)


class TestLijstVanBeschikbareTools:
    async def test_de_lijst_is_het_permissieprofiel_van_de_workflowidentiteit(self) -> None:
        broker = ProductionToolBroker()

        assert sorted(await broker.list_available_tools()) == [
            "create_task",
            "list_tasks",
            "update_task",
        ]

    async def test_de_lijst_bevat_geen_destructieve_tool(self) -> None:
        broker = ProductionToolBroker()

        assert "delete_task" not in await broker.list_available_tools()


class TestHetPermissieprofiel:
    def test_workflow_engine_mag_de_vastgelegde_tools(self) -> None:
        beheer = ToolPermissionManager()

        assert [
            beheer.is_tool_allowed("workflow_engine", t) for t in ("list_tasks", "create_task")
        ] == [True, True]

    def test_workflow_engine_mag_geen_destructieve_of_onbekende_tool(self) -> None:
        beheer = ToolPermissionManager()

        assert [
            beheer.is_tool_allowed("workflow_engine", t)
            for t in ("delete_task", "send_payment_reminder", "x")
        ] == [False, False, False]

    def test_delete_task_staat_op_de_harde_denylist(self) -> None:
        """Dubbele bescherming: ook als iemand `delete_task` per ongeluk in de toegestane lijst zet, blijft hij verboden."""
        assert ToolPermissionManager().is_denied("workflow_engine", "delete_task") is True
