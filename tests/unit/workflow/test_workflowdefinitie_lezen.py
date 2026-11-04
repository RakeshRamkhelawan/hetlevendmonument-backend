"""De engine leest elke vorm waarin een workflowdefinitie echt is opgeslagen (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was (gemeten 2026-10-22 met een echte worker op een workflow met een stap).** De uitvoering faalde met
`AttributeError: 'list' object has no attribute 'items'`. De engine (`WorkflowSpec`) verwacht `tasks` en
`dependencies` als woordenboek (`{taak: instellingen}`, `{taak: [afhankelijkheden]}`). Er komt een LIJST terecht, op twee
manieren:

1. `C7Workflow.spec_json` geeft `self.edges or []`: een workflow met een stap heeft geen afhankelijkheden, dus
   `edges == {}`, en een leeg woordenboek is "onwaar" en werd een lege LIJST;
2. de workflowbuilder en `workflow_service` slaan `nodes` en `edges` op als LIJSTEN (`[{id, type, data}]`,
   `[{id, source, target}]`), de vorm van het canvas.

**Wat hier bewezen wordt.** `_parse_spec` geeft in alle drie de vormen een woordenboek met taken en een
woordenboek met afhankelijkheden, en `to_nodes_and_edges` werkt erop:
- woordenboekvorm (de eigen vorm van de engine): ongewijzigd;
- een lege `{}`/`[]` voor afhankelijkheden (een workflow met een stap);
- de lijstvorm van het canvas: taken op `id`, de instellingen uit `data` op het niveau van de taak (de sleutels van de
  node zelf winnen), afhankelijkheden als `{doel: [bronnen]}`.

**Niet bewezen:** dat de instellingen die de builder in `data` zet de sleutels zijn die een stap nodig heeft
(`prompt`, `tool`, ...). Dat is een productvraag en geen leesvraag.

**Mutatiebewijs:** zie de oplevering van de brief.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.models import C7Workflow
from src.core.workflow.state_machine import WorkflowStateMachine


def _motor() -> ProductionWorkflowEngine:
    return ProductionWorkflowEngine(
        db_session=MagicMock(),
        llm_provider=MagicMock(),
        tool_broker=MagicMock(),
        agent_runtime=MagicMock(),
        state_machine=WorkflowStateMachine(),
    )


def _lees(spec_json: dict[str, Any]) -> Any:
    return _motor()._parse_spec("wf", 1, spec_json)


class TestWoordenboekvorm:
    def test_taken_en_afhankelijkheden_blijven_zoals_ze_zijn(self) -> None:
        spec = _lees(
            {
                "tasks": {"a": {"type": "llm"}, "b": {"type": "tool"}},
                "dependencies": {"b": ["a"]},
            }
        )

        assert (spec.tasks, spec.dependencies) == (
            {"a": {"type": "llm"}, "b": {"type": "tool"}},
            {"b": ["a"]},
        )

    def test_to_nodes_and_edges_werkt_op_de_woordenboekvorm(self) -> None:
        spec = _lees({"tasks": {"a": {"type": "llm"}, "b": {}}, "dependencies": {"b": ["a"]}})

        nodes, edges = spec.to_nodes_and_edges()

        assert ([n["id"] for n in nodes], edges) == (["a", "b"], [{"source": "a", "target": "b"}])


class TestEenWorkflowMetEenStap:
    def test_een_lege_lijst_als_afhankelijkheden_wordt_een_leeg_woordenboek(self) -> None:
        spec = _lees({"tasks": {"stap1": {"type": "llm"}}, "dependencies": []})

        assert spec.dependencies == {}

    def test_een_lege_lijst_als_taken_wordt_een_leeg_woordenboek(self) -> None:
        spec = _lees({"tasks": [], "dependencies": []})

        assert spec.tasks == {}

    def test_het_model_geeft_een_leeg_woordenboek_niet_terug_als_lijst(self) -> None:
        """De bron van het probleem: `self.edges or []` maakte van `{}` een lijst."""
        workflow = C7Workflow(nodes={"stap1": {"type": "llm"}}, edges={})

        spec = _lees(workflow.spec_json)

        assert (spec.tasks, spec.dependencies) == ({"stap1": {"type": "llm"}}, {})

    def test_to_nodes_and_edges_werkt_op_een_workflow_met_een_stap(self) -> None:
        workflow = C7Workflow(nodes={"stap1": {"type": "llm"}}, edges={})

        nodes, edges = _lees(workflow.spec_json).to_nodes_and_edges()

        assert (nodes, edges) == ([{"id": "stap1", "type": "llm"}], [])


class TestDeLijstvormVanHetCanvas:
    _NODES = [
        {"id": "a", "name": "Eerste", "type": "llm", "data": {"prompt": "Zeg hallo"}},
        {"id": "b", "name": "Tweede", "type": "tool", "data": {"tool": "x"}},
    ]
    _EDGES = [{"id": "e1", "source": "a", "target": "b"}]

    def test_nodes_worden_taken_op_id(self) -> None:
        spec = _lees({"tasks": self._NODES, "dependencies": self._EDGES})

        assert sorted(spec.tasks) == ["a", "b"]

    def test_de_instellingen_uit_data_staan_op_het_niveau_van_de_taak(self) -> None:
        spec = _lees({"tasks": self._NODES, "dependencies": self._EDGES})

        assert (spec.tasks["a"]["type"], spec.tasks["a"]["prompt"]) == ("llm", "Zeg hallo")

    def test_een_sleutel_van_de_node_zelf_wint_van_dezelfde_sleutel_in_data(self) -> None:
        spec = _lees(
            {
                "tasks": [{"id": "a", "type": "llm", "data": {"type": "tool"}}],
                "dependencies": [],
            }
        )

        assert spec.tasks["a"]["type"] == "llm"

    def test_edges_worden_afhankelijkheden_per_doel(self) -> None:
        spec = _lees(
            {
                "tasks": self._NODES,
                "dependencies": [
                    {"source": "a", "target": "c"},
                    {"source": "b", "target": "c"},
                ],
            }
        )

        assert spec.dependencies == {"c": ["a", "b"]}

    def test_to_nodes_and_edges_werkt_op_de_lijstvorm(self) -> None:
        spec = _lees({"tasks": self._NODES, "dependencies": self._EDGES})

        nodes, edges = spec.to_nodes_and_edges()

        assert ([n["id"] for n in nodes], edges) == (["a", "b"], [{"source": "a", "target": "b"}])

    def test_een_node_zonder_data_geeft_een_taak_zonder_extra_instellingen(self) -> None:
        spec = _lees({"tasks": [{"id": "a", "type": "llm"}], "dependencies": []})

        assert spec.tasks == {"a": {"id": "a", "type": "llm"}}

    def test_een_dubbele_id_wordt_geweigerd_in_plaats_van_stil_samengevoegd(self) -> None:
        """Gate 2 ronde 1 (M3): bij een dubbele `id` won de laatste node en verdween de eerste zonder fout."""
        with pytest.raises(ValueError, match="Dubbele"):
            _lees(
                {
                    "tasks": [{"id": "a", "type": "llm"}, {"id": "a", "type": "tool"}],
                    "dependencies": [],
                }
            )
