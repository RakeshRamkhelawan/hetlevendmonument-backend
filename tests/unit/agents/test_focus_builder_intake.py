"""
Tests for IntakeEngine + AgentFilter utilities in FocusBuilderChatAgent.

Run: pytest tests/unit/agents/test_focus_builder_intake.py -v
"""

from unittest.mock import AsyncMock, patch

import pytest

# ── AgentFilter utilities ─────────────────────────────────────────────────────


def test_extract_keywords_removes_stopwords():
    from src.core.agents.focus_builder_chat_agent import extract_keywords

    intake = {
        "trigger": "dagelijks 09:00",
        "doel": "debiteuren rapport",
        "output": "email CFO",
    }
    kws = extract_keywords(intake)
    assert "dagelijks" in kws
    assert "debiteuren" in kws
    # stopwords removed
    assert "de" not in kws
    assert "het" not in kws


def test_infer_departments_maps_known_keywords():
    from src.core.agents.focus_builder_chat_agent import infer_departments

    intake = {"trigger": None, "doel": "debiteuren factuur verwerking", "output": None}
    depts = infer_departments(intake)
    assert "finance_treasury" in depts


def test_filter_agents_ranks_by_department_match():
    from src.core.agents.focus_builder_chat_agent import filter_agents

    agents = [
        {
            "id": "a1",
            "name": "Finance Agent",
            "department": "finance_treasury",
            "description": "handles debiteuren",
            "required_integrations": [],
        },
        {
            "id": "a2",
            "name": "HR Agent",
            "department": "hr_culture",
            "description": "handles employees",
            "required_integrations": [],
        },
    ]
    intake = {"trigger": "dagelijks", "doel": "debiteuren rapport", "output": "email"}
    result = filter_agents(intake, agents, live_conns=[], twin_profile={})
    assert result[0]["id"] == "a1"  # finance agent ranked higher


def test_filter_agents_live_connection_boost():
    from src.core.agents.focus_builder_chat_agent import filter_agents

    agents = [
        {
            "id": "a1",
            "name": "Email Agent",
            "department": "sales_marketing",
            "description": "sends email",
            "required_integrations": ["gmail"],
        },
        {
            "id": "a2",
            "name": "Finance Agent",
            "department": "finance_treasury",
            "description": "handles debiteuren",
            "required_integrations": [],
        },
    ]
    intake = {"trigger": "dagelijks", "doel": "debiteuren rapport", "output": "email"}
    live_conns = [{"id": "gmail"}]
    result = filter_agents(intake, agents, live_conns=live_conns, twin_profile={})
    assert result[0]["id"] == "a1"  # live connection gives +10 bonus


def test_filter_agents_fallback_when_no_matches():
    from src.core.agents.focus_builder_chat_agent import filter_agents

    agents = [
        {
            "id": f"a{i}",
            "name": f"Agent {i}",
            "department": "hr_culture",
            "description": "",
            "required_integrations": [],
        }
        for i in range(5)
    ]
    intake = {"trigger": "onbekend", "doel": "xyzzy", "output": "nergens"}
    result = filter_agents(intake, agents, live_conns=[], twin_profile={})
    assert len(result) == 5  # returns all (< 30) when no match


# ── WorkflowGeneratorAgent streaming ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_node_explanation_after_node_proposed():
    """After each node_proposed, a node_explanation event should follow."""
    from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

    events = []

    async def capture(event):
        events.append(event)

    with patch(
        "src.core.services.workflow_generator_service.WorkflowGeneratorAgent._call_llm",
        new=AsyncMock(
            return_value={
                "name": "test_workflow",
                "description": "test",
                "nodes": [
                    {
                        "id": "node_1",
                        "agent_name": "slack_agent",
                        "label": "Slack",
                        "config": {},
                        "position": {"x": 100, "y": 100},
                    }
                ],
                "edges": [],
                "metadata": {},
                "node_explanations": [
                    {
                        "node_id": "node_1",
                        "explanation": "Stuurt een Slack-bericht.",
                        "confidence": "high",
                        "confidence_reason": None,
                    }
                ],
                "suggestion_chips": [],
            }
        ),
    ):
        agent = WorkflowGeneratorAgent(tenant_id=1, correlation_id="test")
        agent._agents_cache = [{"name": "slack_agent", "type": "TECHNICAL", "description": "Slack"}]
        # De generator biedt alleen UITVOERBARE agents aan (agentstap dag 2); deze test gaat over de streamvolgorde.
        agent.get_uitvoerbare_agents = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"name": "slack_agent", "type": "TECHNICAL", "description": "Slack"}]
        )
        await agent.generate_workflow(user_prompt="stuur slack bericht", stream_callback=capture)

    types = [e["type"] for e in events]
    node_proposed_idx = next(i for i, t in enumerate(types) if t == "node_proposed")
    node_explanation_idx = next((i for i, t in enumerate(types) if t == "node_explanation"), None)
    assert node_explanation_idx is not None
    assert node_explanation_idx == node_proposed_idx + 1


# ── IntakeEngine ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_intake_returns_all_fields_when_complete():
    """When LLM extracts all 3 fields, no question is asked."""
    from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent

    agent = FocusBuilderChatAgent(
        user_id=1, tenant_id=1, user_id_str="1", db=AsyncMock(), send_json=AsyncMock()
    )
    with patch.object(
        agent,
        "_call_intake_llm",
        new=AsyncMock(
            return_value={
                "trigger": "dagelijks 09:00",
                "doel": "debiteuren rapport",
                "output": "email CFO",
            }
        ),
    ):
        ctx, question = await agent._run_intake("iedere dag 9:00 debiteuren rapport naar CFO")
    assert ctx["trigger"] is not None
    assert ctx["doel"] is not None
    assert ctx["output"] is not None
    assert question is None  # no question needed


@pytest.mark.asyncio
async def test_run_intake_asks_trigger_question_when_missing():
    """When trigger is missing, asks the trigger question."""
    from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent

    agent = FocusBuilderChatAgent(
        user_id=1, tenant_id=1, user_id_str="1", db=AsyncMock(), send_json=AsyncMock()
    )
    with patch.object(
        agent,
        "_call_intake_llm",
        new=AsyncMock(return_value={"trigger": None, "doel": "rapport", "output": "email"}),
    ):
        ctx, question = await agent._run_intake("maak een rapport")
    assert "Wanneer" in question or "trigger" in question.lower()


@pytest.mark.asyncio
async def test_handle_message_sends_intake_question_event():
    """handle_message sends an intake_question WS event when a field is missing."""
    send = AsyncMock()
    from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent

    agent = FocusBuilderChatAgent(
        user_id=1, tenant_id=1, user_id_str="1", db=AsyncMock(), send_json=send
    )
    agent._twin_profile = {}

    with patch.object(
        agent,
        "_call_intake_llm",
        new=AsyncMock(return_value={"trigger": None, "doel": "rapport", "output": "email"}),
    ):
        await agent.handle_message("maak rapport")

    sent = [c.args[0] for c in send.call_args_list]
    intake_events = [m for m in sent if m.get("type") == "intake_question"]
    assert len(intake_events) == 1
    assert intake_events[0]["step"] == "trigger"
    assert intake_events[0]["progress"] == 1
