"""De stappencontrole van de workflowbuilder (wfb-dag1 stap 1).

Een ActivePieces-flow mag alleen stappen bevatten die NIETS naar buiten sturen en niets vrij
uitvoeren: een trigger of schema, logica (vertakking, lus) en opmaak. Alles wat niet op de
allowlist staat wordt geweigerd -- ook een nieuwe AP-actie die morgen bestaat. Dat is tijdelijk,
tot er per `piece.actie` een risicoregel met HITL bestaat (ADR-040 B12).

Gemeten op twee vormen, want de controle ziet ze allebei:
- de platte vorm die `FlowTransformer` maakt (`trigger` + `actions` per id), bij opslaan;
- de geneste vorm die ActivePieces zelf teruggeeft (`version.trigger.nextAction...`), bij
  aanzetten en uitvoeren van een flow die al in AP staat.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.activepieces.stappencontrole import (
    NietToegestaneStap,
    controleer_flowdefinitie,
    controleer_graaf,
    toegestane_stappen,
)
from src.core.activepieces.transformer import FlowTransformer


def _graaf(*knopen: tuple[str, str], trigger: str | None = None) -> dict[str, Any]:
    """Een React-Flow-graaf: optioneel een trigger, dan de knopen in een rij."""
    nodes: list[dict[str, Any]] = []
    if trigger:
        nodes.append({"id": "start", "agent_name": trigger, "config": {}})
    nodes += [{"id": knoop_id, "agent_name": naam, "config": {}} for knoop_id, naam in knopen]
    ids = [n["id"] for n in nodes]
    edges = [{"source": a, "target": b} for a, b in zip(ids, ids[1:])]
    return {"name": "Test", "nodes": nodes, "edges": edges}


VERBODEN: list[tuple[str, str]] = [
    ("email", "mail"),
    ("slack", "bericht"),
    ("notification_agent", "bericht (discord)"),
    ("http_request", "http"),
    ("database_query", "database"),
    ("mijn_eigen_script", "code (onbekende naam valt terug op piece-code)"),
    ("ap_gmail", "onbekende ap_-actie"),
    ("openai", "gegevens naar een externe dienst"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("agent", "soort"), VERBODEN)
def test_een_verboden_stap_wordt_geweigerd(agent: str, soort: str) -> None:
    with pytest.raises(NietToegestaneStap):
        controleer_graaf(_graaf(("stap1", agent), trigger="schedule"))


@pytest.mark.unit
def test_de_melding_noemt_de_stap_en_verwijst_naar_het_blok_debiteuren() -> None:
    with pytest.raises(NietToegestaneStap) as fout:
        controleer_graaf(_graaf(("brief_versturen", "email")))

    assert "brief_versturen" in str(fout.value) and "Debiteuren" in str(fout.value)


@pytest.mark.unit
def test_een_verboden_stap_als_trigger_wordt_ook_geweigerd() -> None:
    with pytest.raises(NietToegestaneStap):
        controleer_graaf(_graaf(("opmaak", "data_transformer"), trigger="email"))


@pytest.mark.unit
def test_een_flow_met_alleen_toegestane_stappen_slaagt() -> None:
    graaf = _graaf(("opmaak", "data_transformer"), trigger="schedule")
    graaf["nodes"].append({"id": "keuze", "type": "branch", "data": {"conditions": []}})
    graaf["nodes"].append({"id": "lus", "type": "loop", "data": {"items": "{{opmaak}}"}})

    controleer_graaf(graaf)


@pytest.mark.unit
def test_een_handmatige_flow_zonder_trigger_slaagt() -> None:
    controleer_graaf(_graaf(("opmaak", "data_transformer")))


@pytest.mark.unit
def test_een_webhooktrigger_mag() -> None:
    controleer_graaf(_graaf(("opmaak", "data_transformer"), trigger="webhook_trigger"))


def _ap_vorm(stap: dict[str, Any]) -> dict[str, Any]:
    """Zoals ActivePieces een flow teruggeeft: `version.trigger` met geneste `nextAction`."""
    return {
        "id": "flow-1",
        "status": "DISABLED",
        "version": {
            "displayName": "Test",
            "trigger": {
                "name": "trigger",
                "type": "PIECE_TRIGGER",
                "settings": {
                    "pieceName": "@activepieces/piece-schedule",
                    "triggerName": "cron_expression",
                },
                "nextAction": {
                    "name": "opmaak",
                    "type": "PIECE",
                    "settings": {
                        "pieceName": "@activepieces/piece-data-mapper",
                        "actionName": "map_data",
                    },
                    "nextAction": stap,
                },
            },
        },
    }


@pytest.mark.unit
def test_ap_vorm_een_diep_geneste_mailstap_wordt_geweigerd() -> None:
    mail = {
        "name": "mail",
        "type": "PIECE",
        "settings": {"pieceName": "@activepieces/piece-gmail", "actionName": "send_email"},
    }

    with pytest.raises(NietToegestaneStap):
        controleer_flowdefinitie(_ap_vorm(mail))


@pytest.mark.unit
def test_ap_vorm_een_codestap_wordt_geweigerd() -> None:
    code = {"name": "script", "type": "CODE", "settings": {"sourceCode": {"code": "x"}}}

    with pytest.raises(NietToegestaneStap):
        controleer_flowdefinitie(_ap_vorm(code))


@pytest.mark.unit
def test_ap_vorm_een_stap_in_een_routertak_wordt_geweigerd() -> None:
    mail = {
        "name": "mail",
        "type": "PIECE",
        "settings": {"pieceName": "@activepieces/piece-gmail", "actionName": "send_email"},
    }
    router = {"name": "router", "type": "ROUTER", "settings": {}, "children": [None, mail]}

    with pytest.raises(NietToegestaneStap):
        controleer_flowdefinitie(_ap_vorm(router))


@pytest.mark.unit
def test_ap_vorm_met_alleen_toegestane_stappen_slaagt() -> None:
    lus = {"name": "lus", "type": "LOOP_ON_ITEMS", "settings": {"items": "x"}}

    controleer_flowdefinitie(_ap_vorm(lus))


@pytest.mark.unit
def test_een_definitie_zonder_trigger_is_niet_te_controleren_en_wordt_geweigerd() -> None:
    """Fail-closed: herkennen we de vorm niet, dan is dat geen vrijbrief."""
    with pytest.raises(NietToegestaneStap):
        controleer_flowdefinitie({"id": "flow-1", "status": "DISABLED"})


@pytest.mark.unit
def test_een_onbekend_staptype_wordt_geweigerd() -> None:
    vreemd = {"name": "nieuw", "type": "AGENT", "settings": {}}

    with pytest.raises(NietToegestaneStap):
        controleer_flowdefinitie(_ap_vorm(vreemd))


@pytest.mark.unit
def test_elke_toegestane_stap_kan_door_de_builder_gemaakt_worden() -> None:
    """Staleness: een regel op de allowlist die de transformer nooit maakt, bewaakt niets."""
    maakbaar = {
        FlowTransformer._map_agent_to_piece(naam)
        for naam in (
            "email",
            "webhook",
            "schedule",
            "slack",
            "openai",
            "email_agent",
            "slack_agent",
            "http_request",
            "webhook_trigger",
            "schedule_agent",
            "llm_summarizer",
            "sentiment_analyzer",
            "content_generator",
            "database_query",
            "data_transformer",
            "notification_agent",
            "github_integration",
            "jira_integration",
        )
    }

    assert not toegestane_stappen() - maakbaar
