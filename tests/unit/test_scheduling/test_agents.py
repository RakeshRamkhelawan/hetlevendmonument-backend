"""Unit tests for scheduling agents.

Written FIRST (RED) — agents do not exist yet.
Tests define the expected API contract.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSchedulingOrchestratorAgent:
    def test_import_orchestrator_agent(self):
        """The module and class must be importable."""
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        assert SchedulingOrchestratorAgent is not None

    def test_agent_requires_valid_tenant_id(self):
        """Agent must reject tenant_id <= 0."""
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        mock_service = MagicMock()
        with pytest.raises((ValueError, Exception)):
            SchedulingOrchestratorAgent(
                agent_id="test",
                tenant_id=0,
                scheduling_service=mock_service,
            )

    def test_agent_created_with_valid_tenant(self):
        """Agent must construct successfully with a valid tenant_id."""
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        mock_service = MagicMock()
        agent = SchedulingOrchestratorAgent(
            agent_id="sched-1",
            tenant_id=1,
            scheduling_service=mock_service,
        )
        assert agent.tenant_id == 1

    def test_agent_has_scheduling_service(self):
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        mock_service = MagicMock()
        agent = SchedulingOrchestratorAgent(
            agent_id="sched-1",
            tenant_id=1,
            scheduling_service=mock_service,
        )
        assert agent.scheduling_service is mock_service

    @pytest.mark.asyncio
    async def test_format_response_success(self):
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        mock_service = MagicMock()
        agent = SchedulingOrchestratorAgent(
            agent_id="sched-1",
            tenant_id=1,
            scheduling_service=mock_service,
        )
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.event_id = "evt-123"
        msg = agent._format_response(mock_result)
        assert "evt-123" in msg or "gepland" in msg.lower() or "scheduled" in msg.lower()

    @pytest.mark.asyncio
    async def test_format_response_failure(self):
        from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent

        mock_service = MagicMock()
        agent = SchedulingOrchestratorAgent(
            agent_id="sched-1",
            tenant_id=1,
            scheduling_service=mock_service,
        )
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "No slots available"
        msg = agent._format_response(mock_result)
        assert msg  # must return a non-empty string


class TestSchedulingAgentRegistry:
    def test_import_registry(self):
        from src.core.scheduling.agents.registry import SCHEDULING_AGENT_TYPES

        assert isinstance(SCHEDULING_AGENT_TYPES, (list, dict, set, tuple))

    def test_orchestrator_in_registry(self):
        from src.core.scheduling.agents.registry import SCHEDULING_AGENT_TYPES

        names = (
            list(SCHEDULING_AGENT_TYPES)
            if not isinstance(SCHEDULING_AGENT_TYPES, dict)
            else list(SCHEDULING_AGENT_TYPES.keys())
        )
        assert any("orchestrator" in str(n).lower() for n in names)
