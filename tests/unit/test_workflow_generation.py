"""
Tests for WorkflowGeneratorAgent stream_callback — node_proposed events.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.services.workflow_generator_service import WorkflowGeneratorAgent

TWO_NODE_JSON = {
    "name": "Test WF",
    "description": "test",
    "nodes": [
        {
            "id": "n1",
            "agent_name": "slack_agent",
            "label": "Slack",
            "config": {},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n2",
            "agent_name": "email_agent",
            "label": "Email",
            "config": {},
            "position": {"x": 200, "y": 0},
        },
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    "metadata": {},
}


# De generator biedt alleen UITVOERBARE agents aan (agentstap dag 2); deze tests gaan over de events, niet over welke agents
# uitvoerbaar zijn (dat staat in test_workflowgenerator_alleen_uitvoerbare_agents.py).
_UITVOERBAAR = [{"name": naam, "type": "TECHNICAL", "description": "", "source": "test"} for naam in ("slack_agent", "email_agent")]


@pytest.mark.asyncio
async def test_generate_workflow_emits_node_proposed_per_node():
    """stream_callback must receive one node_proposed event per node in the workflow."""
    agent = WorkflowGeneratorAgent(tenant_id=1)
    agent.get_uitvoerbare_agents = AsyncMock(return_value=_UITVOERBAAR)  # type: ignore[method-assign]

    received_events = []

    async def capture_callback(event: dict):
        received_events.append(event)

    with patch.object(agent, "_call_llm", new=AsyncMock(return_value=TWO_NODE_JSON)):
        success, wf, err = await agent.generate_workflow(
            user_prompt="Send Slack then email",
            stream_callback=capture_callback,
        )

    assert success is True
    node_proposed_events = [e for e in received_events if e.get("type") == "node_proposed"]
    assert len(node_proposed_events) == 2
    assert node_proposed_events[0]["node"]["id"] == "n1"
    assert node_proposed_events[1]["node"]["id"] == "n2"
    # Edge connecting to n2 should be in the n2 event
    n2_edges = node_proposed_events[1].get("edges", [])
    assert any(e["source"] == "n1" for e in n2_edges)


@pytest.mark.asyncio
async def test_generate_workflow_emits_proposal_complete():
    """stream_callback must receive proposal_complete after all node_proposed events."""
    agent = WorkflowGeneratorAgent(tenant_id=1)
    agent.get_uitvoerbare_agents = AsyncMock(return_value=_UITVOERBAAR)  # type: ignore[method-assign]

    received_events = []

    async def capture_callback(event: dict):
        received_events.append(event)

    with patch.object(agent, "_call_llm", new=AsyncMock(return_value=TWO_NODE_JSON)):
        await agent.generate_workflow(
            user_prompt="test",
            stream_callback=capture_callback,
        )

    types = [e.get("type") for e in received_events]
    assert "proposal_complete" in types
    proposal_complete = next(e for e in received_events if e.get("type") == "proposal_complete")
    assert proposal_complete["node_count"] == 2
    assert "proposal_id" in proposal_complete


@pytest.mark.asyncio
async def test_generate_workflow_without_callback_still_works():
    """generate_workflow must work fine when no stream_callback is provided."""
    agent = WorkflowGeneratorAgent(tenant_id=1)
    agent.get_uitvoerbare_agents = AsyncMock(return_value=_UITVOERBAAR)  # type: ignore[method-assign]

    with patch.object(agent, "_call_llm", new=AsyncMock(return_value=TWO_NODE_JSON)):
        success, wf, err = await agent.generate_workflow(
            user_prompt="test",
            stream_callback=None,
        )

    assert success is True
    assert wf is not None
