"""De engine leest de definitie zoals de ECHTE workflowbuilder hem opslaat (ADR-036 OP-13, brief 2026-10-22).

**Wat gemeten is (2026-10-22).** `frontend/src/components/WorkflowBuilder.tsx::handleSave` stuurt naar
`POST /api/v1/workflows`:

    spec.tasks        = [{id, name, agent_id, config?}]      (een taak PER node; geen `type`, geen `prompt`)
    spec.dependencies = [{from, to}]                         (geen `source`/`target`)

`WorkflowService.create_workflow` bewaart dat ongewijzigd als `nodes` en `edges` (lijsten). De engine kende alleen
`{taak: instellingen}` en `{taak: [afhankelijkheden]}` en een stap zonder `type` werd stilzwijgend een
taalmodelstap met een lege prompt. Een door de builder gemaakte workflow liep dus nooit goed.

**De bron voor het staptype (besluit, in deze volgorde).**
1. een expliciet `type` van de stap zelf of uit `data`, mits het een staptype is (`llm`, `tool`, `agent`): de
   weergavetypen van het canvas (`custom`, `activepieces`) zijn GEEN staptype en tellen niet;
2. anders afgeleid uit wat de stap heeft: `tool_name` -> `tool`; `agent_id` (of `agentId`) -> `agent`; `prompt` ->
   `llm`;
3. anders blijft er geen geldig type over en de stap faalt zichtbaar met "Unknown task type" in plaats van stil een
   lege taalmodelstap te worden.
De builder zelf zet vandaag alleen `agent_id`: elke node van de builder is dus een AGENTstap.

**Niet bewezen:** dat de agentstap van een builder-node zonder `instruction` iets zinnigs doet (de builder heeft geen
veld daarvoor), en dat een `ap_`-agent (ActivePieces) in deze engine draait; dat loopt via de ActivePieces-route.

**Mutatiebewijs:** zie de oplevering van de brief.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.state_machine import WorkflowStateMachine

# Precies zoals `handleSave` het verstuurt (twee nodes, een verbinding).
BUILDER_TASKS: list[dict[str, Any]] = [
    {"id": "task_1700000000001", "name": "Samenvatten", "agent_id": "summary_agent"},
    {
        "id": "task_1700000000002",
        "name": "Versturen",
        "agent_id": "ap_gmail",
        "config": {"pieceName": "gmail"},
    },
]
BUILDER_DEPENDENCIES: list[dict[str, Any]] = [
    {"from": "task_1700000000001", "to": "task_1700000000002"}
]


def _lees(tasks: Any, dependencies: Any) -> Any:
    motor = ProductionWorkflowEngine(
        db_session=MagicMock(),
        llm_provider=MagicMock(),
        tool_broker=MagicMock(),
        agent_runtime=MagicMock(),
        state_machine=WorkflowStateMachine(),
    )
    return motor._parse_spec("wf", 1, {"tasks": tasks, "dependencies": dependencies})


class TestDeVormVanDeBuilder:
    def test_de_taken_worden_op_id_gelezen_met_hun_agent(self) -> None:
        spec = _lees(BUILDER_TASKS, BUILDER_DEPENDENCIES)

        assert {k: v["agent_id"] for k, v in spec.tasks.items()} == {
            "task_1700000000001": "summary_agent",
            "task_1700000000002": "ap_gmail",
        }

    def test_een_builder_node_is_een_agentstap(self) -> None:
        spec = _lees(BUILDER_TASKS, BUILDER_DEPENDENCIES)

        assert {v["type"] for v in spec.tasks.values()} == {"agent"}

    def test_de_verbinding_van_de_builder_wordt_een_afhankelijkheid(self) -> None:
        spec = _lees(BUILDER_TASKS, BUILDER_DEPENDENCIES)

        assert spec.dependencies == {"task_1700000000002": ["task_1700000000001"]}

    def test_de_definitie_van_de_builder_is_een_geldige_graaf(self) -> None:
        nodes, edges = _lees(BUILDER_TASKS, BUILDER_DEPENDENCIES).to_nodes_and_edges()

        assert ([n["type"] for n in nodes], edges) == (
            ["agent", "agent"],
            [{"source": "task_1700000000001", "target": "task_1700000000002"}],
        )

    def test_een_node_zonder_verbindingen_is_een_geldige_workflow_met_een_stap(self) -> None:
        spec = _lees(BUILDER_TASKS[:1], [])

        assert (list(spec.tasks), spec.dependencies) == (["task_1700000000001"], {})


class TestDeBronVanHetStaptype:
    def test_een_expliciet_staptype_wint_van_afleiden(self) -> None:
        spec = _lees([{"id": "a", "type": "tool", "agent_id": "x"}], [])

        assert spec.tasks["a"]["type"] == "tool"

    def test_een_staptype_in_data_telt_ook(self) -> None:
        spec = _lees([{"id": "a", "data": {"type": "llm", "prompt": "hoi"}}], [])

        assert spec.tasks["a"]["type"] == "llm"

    def test_een_weergavetype_van_het_canvas_is_geen_staptype(self) -> None:
        spec = _lees([{"id": "a", "type": "custom", "data": {"agentId": "summary_agent"}}], [])

        assert spec.tasks["a"]["type"] == "agent"

    def test_tool_name_geeft_een_toolstap(self) -> None:
        spec = _lees([{"id": "a", "tool_name": "list_tasks"}], [])

        assert spec.tasks["a"]["type"] == "tool"

    def test_een_prompt_geeft_een_taalmodelstap(self) -> None:
        spec = _lees([{"id": "a", "prompt": "Zeg hallo"}], [])

        assert spec.tasks["a"]["type"] == "llm"

    def test_agentid_van_het_canvas_wordt_agent_id(self) -> None:
        spec = _lees([{"id": "a", "data": {"agentId": "summary_agent"}}], [])

        assert spec.tasks["a"]["agent_id"] == "summary_agent"

    def test_zonder_enig_kenmerk_blijft_het_weergavetype_staan_en_faalt_de_stap_zichtbaar(
        self,
    ) -> None:
        spec = _lees([{"id": "a", "type": "custom"}], [])

        assert spec.tasks["a"]["type"] == "custom"

    def test_de_woordenboekvorm_van_de_engine_blijft_ongemoeid(self) -> None:
        spec = _lees({"a": {"type": "llm", "prompt": "x"}}, {"b": ["a"]})

        assert (spec.tasks, spec.dependencies) == (
            {"a": {"type": "llm", "prompt": "x"}},
            {"b": ["a"]},
        )
