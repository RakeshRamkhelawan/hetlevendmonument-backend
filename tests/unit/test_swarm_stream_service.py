# -*- coding: utf-8 -*-
"""
Unit Tests for SwarmStreamService

Tests agent role management, status updates, event streaming, and feedback loops.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from src.core.services.swarm_stream_service import (
    AgentRole,
    AgentStatus,
    EventType,
    SwarmAgent,
    SwarmEvent,
    SwarmSession,
    SwarmStreamService,
    create_swarm_service,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """Create a fresh SwarmStreamService instance."""
    return create_swarm_service(tenant_id=1)


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# SwarmStreamService Tests
# ============================================================================


class TestSwarmStreamService:
    """Tests for SwarmStreamService core functionality."""

    def test_create_service(self):
        """Test service creation with tenant ID."""
        service = create_swarm_service(tenant_id=42)
        assert service.tenant_id == 42
        assert len(service._sessions) == 0

    @pytest.mark.asyncio
    async def test_start_swarm_creates_session(self, service):
        """Test starting a swarm creates a valid session."""
        session = await service.start_swarm("Test objective")

        assert session is not None
        assert session.id is not None
        assert session.tenant_id == 1
        assert session.objective == "Test objective"
        assert session.status == "active"

    @pytest.mark.asyncio
    async def test_start_swarm_auto_spawns_agents(self, service):
        """Test auto-spawn creates all three agent roles."""
        session = await service.start_swarm("Test", auto_spawn=True)

        assert len(session.agents) == 3
        roles = {a.role for a in session.agents.values()}
        assert AgentRole.ORCHESTRATOR in roles
        assert AgentRole.RESEARCHER in roles
        assert AgentRole.EXECUTOR in roles

    @pytest.mark.asyncio
    async def test_start_swarm_no_auto_spawn(self, service):
        """Test starting without auto-spawn creates no agents."""
        session = await service.start_swarm("Test", auto_spawn=False)

        assert len(session.agents) == 0

    @pytest.mark.asyncio
    async def test_swarm_events_emitted(self, service):
        """Test events are emitted during swarm start."""
        events_received = []

        async def callback(event):
            events_received.append(event)

        service.add_event_callback(callback)
        await service.start_swarm("Test objective")

        assert len(events_received) >= 4  # 1 start + 3 spawns
        assert events_received[0].type == EventType.SWARM_STARTED

    @pytest.mark.asyncio
    async def test_agent_status_update(self, service):
        """Test agent status updates emit events."""
        events_received = []

        async def callback(event):
            events_received.append(event)

        service.add_event_callback(callback)
        session = await service.start_swarm("Test")

        agent = list(session.agents.values())[0]
        initial_count = len(events_received)

        await service._update_agent_status(session, agent, AgentStatus.THINKING, "Analyzing")

        assert agent.status == AgentStatus.THINKING
        assert agent.current_task == "Analyzing"
        assert len(events_received) > initial_count

    @pytest.mark.asyncio
    async def test_execute_swarm_simulation(self, service):
        """Test simulated swarm execution completes successfully."""
        session = await service.start_swarm("Optimize performance")
        result = await service.execute_swarm(session, simulate=True)

        assert result["success"] is True
        assert session.status == "complete"
        assert len(session.events) > 0

    @pytest.mark.asyncio
    async def test_get_session(self, service):
        """Test retrieving a session by ID."""
        session = await service.start_swarm("Test")

        retrieved = service.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, service):
        """Test listing active sessions."""
        await service.start_swarm("Test 1")
        await service.start_swarm("Test 2")

        active = service.get_active_sessions()
        assert len(active) == 2

    def test_remove_event_callback(self, service):
        """Test removing an event callback."""

        def callback(e):
            pass

        service.add_event_callback(callback)
        assert callback in service._event_callbacks

        service.remove_event_callback(callback)
        assert callback not in service._event_callbacks


# ============================================================================
# Agent Tests
# ============================================================================


class TestSwarmAgent:
    """Tests for SwarmAgent data class."""

    def test_agent_to_dict(self):
        """Test agent serialization."""
        agent = SwarmAgent(
            id="test-123",
            role=AgentRole.ORCHESTRATOR,
            name="Test Agent",
            status=AgentStatus.EXECUTING,
            current_task="Testing",
        )

        data = agent.to_dict()

        assert data["id"] == "test-123"
        assert data["role"] == "orchestrator"
        assert data["name"] == "Test Agent"
        assert data["status"] == "executing"
        assert data["current_task"] == "Testing"

    def test_agent_default_values(self):
        """Test agent default values."""
        agent = SwarmAgent(id="test", role=AgentRole.RESEARCHER, name="Researcher")

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None
        assert agent.messages == []


# ============================================================================
# Event Tests
# ============================================================================


class TestSwarmEvent:
    """Tests for SwarmEvent data class."""

    def test_event_to_dict(self):
        """Test event serialization."""
        event = SwarmEvent(
            id="event-123",
            type=EventType.AGENT_MESSAGE,
            timestamp=datetime(2024, 12, 27, 12, 0, 0, tzinfo=timezone.utc),
            agent_id="agent-1",
            agent_role=AgentRole.EXECUTOR,
            message="Test message",
            data={"key": "value"},
        )

        data = event.to_dict()

        assert data["id"] == "event-123"
        assert data["type"] == "agent_message"
        assert data["agent_role"] == "executor"
        assert data["message"] == "Test message"
        assert data["data"] == {"key": "value"}


# ============================================================================
# Session Tests
# ============================================================================


class TestSwarmSession:
    """Tests for SwarmSession data class."""

    def test_session_to_dict(self):
        """Test session serialization."""
        session = SwarmSession(id="session-123", tenant_id=1, objective="Test objective")

        data = session.to_dict()

        assert data["id"] == "session-123"
        assert data["tenant_id"] == 1
        assert data["objective"] == "Test objective"
        assert data["status"] == "active"


# ============================================================================
# Feedback Tests
# ============================================================================


class TestFeedbackLoop:
    """Tests for feedback loop functionality."""

    @pytest.mark.asyncio
    async def test_submit_feedback(self, service):
        """Test submitting feedback resolves pending request."""
        session = await service.start_swarm("Test")
        agent = list(session.agents.values())[0]

        # Create feedback future
        feedback_id = "test-feedback"
        future = asyncio.get_event_loop().create_future()
        service._feedback_handlers[feedback_id] = future

        # Submit feedback
        service.submit_feedback(feedback_id, "approved")

        result = await future
        assert result == "approved"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_callback_error_handling(self, service):
        """Test that callback errors don't break event emission."""
        error_count = [0]

        async def bad_callback(event):
            error_count[0] += 1
            raise ValueError("Intentional error")

        async def good_callback(event):
            pass

        service.add_event_callback(bad_callback)
        service.add_event_callback(good_callback)

        # Should not raise despite bad callback
        await service.start_swarm("Test")

        assert error_count[0] > 0  # Bad callback was called

    def test_get_nonexistent_session(self, service):
        """Test getting a session that doesn't exist."""
        result = service.get_session("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self):
        """Test that different tenants have isolated sessions."""
        service1 = create_swarm_service(tenant_id=1)
        service2 = create_swarm_service(tenant_id=2)

        session1 = await service1.start_swarm("Tenant 1 task")
        session2 = await service2.start_swarm("Tenant 2 task")

        assert session1.tenant_id == 1
        assert session2.tenant_id == 2

        # Each service only sees its own sessions
        assert len(service1.get_active_sessions()) == 1
        assert len(service2.get_active_sessions()) == 1
