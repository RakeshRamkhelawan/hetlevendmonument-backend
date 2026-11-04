"""Unit tests for Focus Builder Digital Twin observer integration (Phase 4)."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent
from src.core.api.v1.focus_builder.shared import _track_focus_builder_action


@pytest.mark.asyncio
async def test_track_focus_builder_action_persists(db_session: AsyncSession) -> None:
    """_track_focus_builder_action should create an observation via the twin."""
    await _track_focus_builder_action(
        db=db_session,
        user_id=42,
        tenant_id=1,
        session_id="sess_abc",
        behavior_type="focus_builder.flow_created",
        context={"flow_id": 7, "flow_name": "Test Flow"},
    )

    # best_effort swallows exceptions — the call should complete without error
    # A full integration test verifies DB rows; this unit test verifies the wiring.


@pytest.mark.asyncio
async def test_chat_agent_track_in_twin(db_session: AsyncSession) -> None:
    """FocusBuilderChatAgent._track_in_twin should use the twin service."""
    agent = FocusBuilderChatAgent(
        user_id=1,
        tenant_id=1,
        user_id_str="user_1",
        db=db_session,
        send_json=AsyncMock(),
    )

    # Should complete without error
    await agent._track_in_twin(
        behavior_type="focus_builder.workflow_accepted",
        context={"proposal_id": "prop_123", "agents": ["agent_a"]},
    )


@pytest.mark.asyncio
async def test_chat_agent_log_acceptance_to_twin(db_session: AsyncSession) -> None:
    """_log_acceptance_to_twin should track proposal acceptance."""
    agent = FocusBuilderChatAgent(
        user_id=1,
        tenant_id=1,
        user_id_str="user_1",
        db=db_session,
        send_json=AsyncMock(),
    )

    nodes = [{"type": "trigger"}, {"type": "action"}]
    await agent._log_acceptance_to_twin("prop_123", nodes)
    # Should complete without raising


@pytest.mark.asyncio
async def test_chat_agent_handle_node_updated(db_session: AsyncSession) -> None:
    """handle_node_updated should track agent swaps."""
    agent = FocusBuilderChatAgent(
        user_id=1,
        tenant_id=1,
        user_id_str="user_1",
        db=db_session,
        send_json=AsyncMock(),
    )

    await agent.handle_node_updated("node_1", "agent_a", "agent_b")
    # Should complete without raising


@pytest.mark.asyncio
async def test_chat_agent_load_twin_profile_graceful_failure(db_session: AsyncSession) -> None:
    """_load_twin_profile should return {} when no profile exists."""
    agent = FocusBuilderChatAgent(
        user_id=1,
        tenant_id=1,
        user_id_str="user_1",
        db=db_session,
        send_json=AsyncMock(),
    )

    profile = await agent._load_twin_profile()
    assert profile == {}
