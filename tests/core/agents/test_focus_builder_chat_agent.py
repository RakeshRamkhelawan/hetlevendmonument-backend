# tests/core/agents/test_focus_builder_chat_agent.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.mark.asyncio
async def test_session_init_includes_connected_apps(mock_db):
    sent = []

    async def send_json(data):
        sent.append(data)

    with patch(
        "src.core.agents.focus_builder_chat_agent.get_connected_apps",
        new_callable=AsyncMock,
        return_value=["teams", "asana"],
    ):
        agent = FocusBuilderChatAgent(
            user_id=1,
            tenant_id=1,
            user_id_str="1",
            db=mock_db,
            send_json=send_json,
        )
        await agent.start_session()

    init_event = next(e for e in sent if e.get("type") == "session_init")
    assert init_event["connected_apps"] == ["teams", "asana"]
    assert "proactive_suggestions" in init_event
    assert "twin_summary" in init_event


@pytest.mark.asyncio
async def test_session_init_connected_apps_timeout_fallback(mock_db):
    """On AP timeout, connected_apps=[] but session_init still sent."""
    sent = []

    async def send_json(data):
        sent.append(data)

    with patch(
        "src.core.agents.focus_builder_chat_agent.get_connected_apps",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError(),
    ):
        agent = FocusBuilderChatAgent(
            user_id=1,
            tenant_id=1,
            user_id_str="1",
            db=mock_db,
            send_json=send_json,
        )
        await agent.start_session()

    init_event = next(e for e in sent if e.get("type") == "session_init")
    assert init_event["connected_apps"] == []
    assert init_event["proactive_suggestions"] == []

# ---------------------------------------------------------------------------
# Herschreven 2026-08-30 -- zeven tests beschreven een agent die niet meer bestaat.
#
# `b1897b4c` heeft `focus_builder_chat_agent.py` herschreven: de oude flow met
# `progress_step`, `choice_form`, een chirurgische refine-modus en
# `_stream_text_response` is vervangen door een intake- en template-flow. De tests
# hieronder zijn daar niet in meegegaan en stonden sindsdien rood -- lang genoeg om als
# "bekende failure" gelezen te worden, wat ze als bewaking waardeloos maakte.
#
# Waar het BEDOELDE gedrag nog bestaat, is de test verplaatst naar de nieuwe plek. Waar
# het gedrag echt weg is, is de test verwijderd en is de discrepantie vastgelegd in
# `tests/architecture/test_focus_builder_ws_contract.py`, dat de berichttypen aan beide
# kanten vergelijkt. Verwijderde dekking wordt daar dus zichtbaar in plaats van stil.
#
# Verwijderd, met reden:
# - test_generate_emits_progress_steps      -> `progress_step` wordt nergens meer verstuurd
# - test_needs_more_context_emits_choice_form -> `choice_form` idem
# - test_pending_choice_blocks_second_choice_form -> idem
# - test_handle_refine_calls_surgical_generator -> refine doet nu een volledige generatie
#
# NIET verwijderd maar OPENSTAAND: `test_handle_refine_rejects_oversized_workflow` toetste
# een beveiliging die met de herschrijving is verdwenen -- refine had een bovengrens en
# stuurde `patch_error`/`workflow_too_large` bij meer dan een handvol nodes. Die grens
# bestaat niet meer; `handle_refine` geeft nu elk aantal nodes door. Dat is geen
# testonderhoud maar een teruggedraaide beveiliging, en die hoort met een eigen besluit
# terug te komen -- zie het auditrapport van 2026-08-30.
# ---------------------------------------------------------------------------


def test_filter_agents_prefers_a_live_integration():
    """De live verbindingen sturen nu de agent-RANGSCHIKKING, niet meer de session_init-payload.

    Dit is waar het signaal "welke apps heeft deze klant aangesloten" in het nieuwe ontwerp
    terechtkomt (`filter_agents`, +10 punten). De oude test toetste dat hetzelfde signaal in
    de systeemprompt van `_build_system_context` stond; die plek bestaat niet meer, de
    bedoeling wel.
    """
    from src.core.agents.focus_builder_chat_agent import filter_agents

    intake = {"trigger": "email", "doel": "melden", "output": "bericht"}
    agents = [
        {"id": "a", "name": "Alpha", "description": "", "department": "", "required_integrations": []},
        {"id": "b", "name": "Beta", "description": "", "department": "", "required_integrations": ["slack"]},
    ]

    zonder = filter_agents(intake=intake, all_agents=agents, live_conns=[], twin_profile={})
    met = filter_agents(
        intake=intake, all_agents=agents, live_conns=[{"id": "slack"}], twin_profile={}
    )

    assert [a["id"] for a in met][0] == "b", (
        "Een agent die een LIVE aangesloten integratie nodig heeft hoort bovenaan te staan; "
        "dat is de +10 in `filter_agents`."
    )
    assert len(zonder) == len(met) == 2, "Zonder live verbinding mag er niets wegvallen."


@pytest.mark.asyncio
async def test_handle_explain_sends_an_explanation_and_generates_nothing(mock_db):
    """Uitleg vragen mag nooit een workflow-generatie starten.

    Zelfde bedoeling als de oude test; die patchte `_stream_text_response`, een methode die
    met de herschrijving is verdwenen. Nu getoetst op wat er WEL gebeurt: een
    `node_explanation`-bericht, en geen enkele aanroep van de generator.
    """
    sent = []

    async def send_json(data):
        sent.append(data)

    with (
        patch.object(
            FocusBuilderChatAgent,
            "_explain_node_llm",
            new_callable=AsyncMock,
            return_value=("Dit stuurt een e-mail.", "high"),
        ),
        patch("src.core.agents.focus_builder_chat_agent.WorkflowGeneratorAgent") as MockGen,
    ):
        agent = FocusBuilderChatAgent(
            user_id=1,
            tenant_id=1,
            user_id_str="1",
            db=mock_db,
            send_json=send_json,
        )
        await agent.handle_explain(node_id="1", node_title="Email sturen", node_type="action")

    uitleg = [e for e in sent if e.get("type") == "node_explanation"]
    assert len(uitleg) == 1, f"Verwacht een node_explanation, kreeg: {[e.get('type') for e in sent]}"
    assert uitleg[0]["node_id"] == "1"
    MockGen.assert_not_called()
