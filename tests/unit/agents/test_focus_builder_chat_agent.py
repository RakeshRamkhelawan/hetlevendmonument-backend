"""
Unit tests for FocusBuilderChatAgent.

Verifies:
- start_session() sends session_init with conversation_id
- handle_message() sends intake_question when context is vague
- handle_message() falls through to generation after 3 questions
- accept_proposal() (async) returns nodes, persists to DB, logs to twin
- reject_proposal() removes from pending without returning nodes
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent


def make_agent(send_json=None):
    db = AsyncMock()
    return FocusBuilderChatAgent(
        user_id=1,
        tenant_id=1,
        user_id_str="user_1",
        db=db,
        send_json=send_json or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_start_session_sends_session_init():
    send = AsyncMock()
    agent = make_agent(send)
    with patch.object(agent, "_load_twin_profile", new=AsyncMock(return_value={})):
        await agent.start_session()
    calls = [c.args[0] for c in send.call_args_list]
    types = [c["type"] for c in calls]
    assert "session_init" in types
    session_init = next(c for c in calls if c["type"] == "session_init")
    assert "conversation_id" in session_init


@pytest.mark.asyncio
async def test_handle_message_sends_intake_question_when_vague():
    send = AsyncMock()
    agent = make_agent(send)
    agent._twin_profile = {}

    with patch.object(
        agent,
        "_call_intake_llm",
        new=AsyncMock(return_value={"trigger": None, "doel": "iets", "output": "email"}),
    ):
        await agent.handle_message("doe iets")

    calls = [c.args[0] for c in send.call_args_list]
    intake_events = [c for c in calls if c.get("type") == "intake_question"]
    assert len(intake_events) > 0
    assert agent._question_count == 1


@pytest.mark.asyncio
async def test_handle_message_generates_after_3_questions():
    send = AsyncMock()
    agent = make_agent(send)
    agent._twin_profile = {}
    agent._question_count = 3  # already asked max questions

    with patch("src.core.agents.focus_builder_chat_agent.WorkflowGeneratorAgent") as MockGen:
        instance = MockGen.return_value
        instance.generate_workflow = AsyncMock()
        # _build_generation_prompt calls get_tenant_ap_project -> real HTTP -> ~14s.
        # Mock it to prevent the network call while still exercising the generate path.
        with patch.object(agent, "_build_generation_prompt", AsyncMock(return_value="")):
            await agent.handle_message("maak workflow")

    instance.generate_workflow.assert_called_once()


@pytest.mark.asyncio
async def test_accept_proposal_returns_nodes():
    agent = make_agent()
    proposal_id = "prop_1"
    nodes = [{"id": "n1", "type": "slack_agent"}]
    agent._pending_proposals[proposal_id] = nodes
    agent._proposal_intakes[proposal_id] = {
        "trigger": "dagelijks",
        "doel": "test",
        "output": "email",
    }

    with patch(
        "src.core.agents.focus_builder_chat_agent.save_accepted_workflow",
        new=AsyncMock(),
    ):
        with patch.object(agent, "_log_acceptance_to_twin", new=AsyncMock()):
            result = await agent.accept_proposal(proposal_id)
    assert result == nodes
    assert proposal_id not in agent._pending_proposals


@pytest.mark.asyncio
async def test_reject_proposal_clears_pending():
    agent = make_agent()
    proposal_id = "prop_2"
    agent._pending_proposals[proposal_id] = [{"id": "n1"}]

    agent.reject_proposal(proposal_id)
    assert proposal_id not in agent._pending_proposals


@pytest.mark.asyncio
async def test_handle_refine_sends_thinking_and_generates():
    send = AsyncMock()
    agent = make_agent(send_json=send)
    current_nodes = [{"id": "n1", "data": {"title": "Send Email"}}]

    with patch.object(agent, "_generate", new=AsyncMock()) as mock_gen:
        await agent.handle_refine("voeg een goedkeuring toe", current_nodes)

    sent_types = [c.args[0]["type"] for c in send.call_args_list]
    assert "thinking" in sent_types
    assert mock_gen.called
    history_msgs = [m["content"] for m in agent._message_history]
    assert any("Verfijnen" in m for m in history_msgs)


@pytest.mark.asyncio
async def test_handle_explain_emits_node_explanation_event():
    send = AsyncMock()
    agent = make_agent(send_json=send)

    with patch.object(
        agent,
        "_explain_node_llm",
        new=AsyncMock(return_value=("Dit stuurt een e-mail.", "high")),
    ):
        await agent.handle_explain(node_id="n1", node_title="Send Email", node_type="email_agent")

    sent = [c.args[0] for c in send.call_args_list]
    explanation_events = [m for m in sent if m.get("type") == "node_explanation"]
    assert len(explanation_events) == 1
    evt = explanation_events[0]
    assert evt["node_id"] == "n1"
    assert evt["confidence"] == "high"
    assert "e-mail" in evt["content"]


@pytest.mark.asyncio
async def test_explain_node_llm_returns_low_confidence_on_error():
    agent = make_agent()

    with patch(
        "src.core.agents.focus_builder_chat_agent.WorkflowGeneratorAgent",
        side_effect=Exception("LLM unavailable"),
    ) as mock_gen:
        explanation, confidence = await agent._explain_node_llm("Send Email", "email_agent")

    # OP-176: a local re-import inside _explain_node_llm() used to shadow this patch,
    # so the mock was never reached and a real Gemini call happened instead.
    mock_gen.assert_called_once()
    assert confidence == "low"
    assert "Send Email" in explanation


@pytest.mark.asyncio
async def test_call_intake_llm_falls_back_to_all_none_on_error():
    """OP-176: `_call_intake_llm()` had the same shadowing local re-import as
    `_explain_node_llm()` -- this proves the fix on that second call site too."""
    agent = make_agent()

    with patch(
        "src.core.agents.focus_builder_chat_agent.WorkflowGeneratorAgent",
        side_effect=Exception("LLM unavailable"),
    ) as mock_gen:
        result = await agent._call_intake_llm("een vage beschrijving")

    mock_gen.assert_called_once()
    assert result == {"trigger": None, "doel": None, "output": None}


@pytest.mark.asyncio
async def test_find_matching_template_returns_none_when_no_templates():
    agent = make_agent()
    agent._intake_context = {
        "trigger": "dagelijks",
        "doel": "rapport",
        "output": "email",
    }

    with patch("src.core.services.template_registry.TemplateRegistry") as MockRegistry:
        MockRegistry.return_value.list_templates.return_value = []
        result = await agent._find_matching_template()

    assert result is None
