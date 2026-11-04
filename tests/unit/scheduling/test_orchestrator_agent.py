"""Tests for the scheduling orchestrator agent."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduling.agents.orchestrator_agent import SchedulingOrchestratorAgent
from src.core.shared.interfaces import ExecutionResult


class TestSchedulingOrchestratorAgent:
    """Test suite for SchedulingOrchestratorAgent."""

    @pytest.fixture
    def mock_scheduling_service(self) -> MagicMock:
        """Create a mocked SchedulingService."""
        return MagicMock()

    @pytest.fixture
    def agent(self, mock_scheduling_service: MagicMock) -> SchedulingOrchestratorAgent:
        """Create a SchedulingOrchestratorAgent instance."""
        return SchedulingOrchestratorAgent(
            agent_id="test_orchestrator",
            tenant_id=1,
            scheduling_service=mock_scheduling_service,
        )

    @pytest.mark.asyncio
    async def test_create_factory_method(self) -> None:
        """Test the factory method for creating agent instances."""
        db_session = AsyncMock()

        with patch(
            "src.core.scheduling.agents.orchestrator_agent.SchedulingService"
        ) as mock_service_class:
            mock_service_class.return_value = MagicMock()
            agent = await SchedulingOrchestratorAgent.create(
                tenant_id=1,
                db_session=db_session,
            )

            assert agent.tenant_id == 1
            assert agent.agent_id == "scheduling_orchestrator_1"
            mock_service_class.assert_called_once_with(db_session)

    @pytest.mark.asyncio
    async def test_observe_extracts_request_parameters(
        self, agent: SchedulingOrchestratorAgent
    ) -> None:
        """Test observe phase extracts and structures request data."""
        request_data = {
            "title": "Team Standup",
            "duration_minutes": 30,
            "participants": ["user1", "user2"],
            "preferred_dates": ["2026-03-20"],
            "time_range": {"start": "09:00", "end": "17:00"},
            "priority": 5,
            "constraints": [{"type": "hard"}],
        }

        observation = await agent.observe(request_data)

        assert observation["tenant_id"] == 1
        assert observation["agent_id"] == "test_orchestrator"
        assert observation["request"]["title"] == "Team Standup"
        assert observation["request"]["duration_minutes"] == 30
        assert observation["context"]["participant_count"] == 2
        assert observation["context"]["has_time_preference"] is True
        assert observation["context"]["has_date_preference"] is True

    @pytest.mark.asyncio
    async def test_observe_default_values(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test observe phase applies defaults for missing fields."""
        request_data = {}

        observation = await agent.observe(request_data)

        assert observation["request"]["title"] == "Untitled Meeting"
        assert observation["request"]["duration_minutes"] == 30
        assert observation["request"]["participants"] == []
        assert observation["context"]["participant_count"] == 0
        assert observation["context"]["has_time_preference"] is False
        assert observation["context"]["has_date_preference"] is False

    @pytest.mark.asyncio
    async def test_orient_analyzes_context(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test orient phase analyzes constraints and complexity."""
        observation = {
            "request": {
                "title": "Team Meeting",
                "duration_minutes": 60,
                "participants": ["user1", "user2", "user3"],
                "preferred_dates": ["2026-03-20"],
                "time_range": {"start": "09:00", "end": "17:00"},
                "priority": 3,
                "constraints": [
                    {"type": "hard"},
                    {"type": "soft"},
                ],
            }
        }

        orientation = await agent.orient(observation)

        assert "analysis" in orientation
        assert "complexity_score" in orientation["analysis"]
        assert "urgency_level" in orientation["analysis"]
        assert "flexibility_score" in orientation["analysis"]
        assert orientation["analysis"]["complexity_score"] > 0

    @pytest.mark.asyncio
    async def test_decide_high_urgency_strategy(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test decide phase chooses immediate schedule for high priority."""
        orientation = {
            "analysis": {
                "complexity_score": 0.5,
                "urgency_level": "high",
                "flexibility_score": 0.3,
            },
            "strategy_hints": {
                "use_smart_scheduling": False,
                "check_all_participants": False,
                "enforce_hard_constraints": False,
            },
        }

        decision = await agent.decide(orientation)

        assert decision == "schedule_immediate"

    @pytest.mark.asyncio
    async def test_decide_smart_scheduling_strategy(
        self, agent: SchedulingOrchestratorAgent
    ) -> None:
        """Test decide phase chooses smart scheduling for multi-participant."""
        orientation = {
            "analysis": {
                "complexity_score": 0.3,
                "urgency_level": "medium",
                "flexibility_score": 0.7,
            },
            "strategy_hints": {
                "use_smart_scheduling": True,
                "check_all_participants": True,
                "enforce_hard_constraints": False,
            },
        }

        decision = await agent.decide(orientation)

        assert decision == "schedule_smart"

    @pytest.mark.asyncio
    async def test_act_success(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test act phase successfully executes scheduling."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.event_id = "event_123"
        mock_result.scheduled_event_id = "event_123"

        agent.scheduling_service.schedule_meeting = AsyncMock(return_value=mock_result)

        # Use realistic date/time range for request
        now = datetime.now(timezone.utc)
        start_time = now + __import__("datetime").timedelta(days=1)
        end_time = start_time + __import__("datetime").timedelta(hours=1)

        orientation = {
            "observation": {
                "request": {
                    "title": "Team Meeting",
                    "duration_minutes": 60,
                    "participants": ["user1"],
                    "preferred_dates": [start_time.isoformat()],
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                    },
                    "priority": 3,
                }
            }
        }

        result = await agent.act("schedule_standard", orientation)

        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_act_failure_handling(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test act phase handles scheduling failure gracefully."""
        agent.scheduling_service.schedule_meeting = AsyncMock(
            side_effect=Exception("Scheduling failed")
        )

        orientation = {
            "observation": {
                "request": {
                    "title": "Team Meeting",
                    "duration_minutes": 60,
                    "participants": ["user1"],
                    "preferred_dates": None,
                    "time_range": None,
                    "priority": 3,
                }
            }
        }

        result = await agent.act("schedule_standard", orientation)

        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert "Scheduling failed" in result.error_message

    @pytest.mark.asyncio
    async def test_process_scheduling_request_full_ooda_loop(
        self, agent: SchedulingOrchestratorAgent
    ) -> None:
        """Test full OODA loop from request to result."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.event_id = "event_456"

        agent.scheduling_service.schedule_meeting = AsyncMock(return_value=mock_result)

        request_data = {
            "title": "Weekly Sync",
            "duration_minutes": 30,
            "participants": ["user1", "user2"],
            "priority": 5,
        }

        result = await agent.process_scheduling_request(request_data)

        assert isinstance(result, ExecutionResult)

    def test_calculate_complexity_high(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test complexity calculation for high-complexity request."""
        request = {
            "participants": ["u1", "u2", "u3", "u4", "u5", "u6"],
            "constraints": [
                {"type": "hard"},
                {"type": "hard"},
                {"type": "hard"},
                {"type": "hard"},
            ],
            "preferred_dates": ["2026-03-20"],
            "time_range": {"start": "09:00", "end": "17:00"},
        }

        complexity = agent._calculate_complexity(request)

        assert 0.0 <= complexity <= 1.0
        assert complexity > 0.5

    def test_calculate_complexity_low(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test complexity calculation for low-complexity request."""
        request = {
            "participants": ["u1"],
            "constraints": [],
            "preferred_dates": None,
            "time_range": None,
        }

        complexity = agent._calculate_complexity(request)

        assert 0.0 <= complexity <= 1.0
        assert complexity <= 0.3

    def test_assess_urgency_high_priority(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test urgency assessment for high priority."""
        request = {"priority": 9}

        urgency = agent._assess_urgency(request)

        assert urgency == "high"

    def test_assess_urgency_medium_priority(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test urgency assessment for medium priority."""
        request = {"priority": 5}

        urgency = agent._assess_urgency(request)

        assert urgency == "medium"

    def test_assess_urgency_low_priority(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test urgency assessment for low priority."""
        request = {"priority": 2}

        urgency = agent._assess_urgency(request)

        assert urgency == "low"

    def test_assess_flexibility_constrained(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test flexibility assessment for highly constrained request."""
        request = {
            "preferred_dates": ["2026-03-20", "2026-03-21"],
            "time_range": {"start": "14:00", "end": "15:00"},
            "constraints": [
                {"type": "hard"},
                {"type": "hard"},
            ],
        }

        flexibility = agent._assess_flexibility(request)

        assert 0.0 <= flexibility <= 1.0
        assert flexibility < 0.5

    def test_assess_flexibility_unconstrained(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test flexibility assessment for flexible request."""
        request = {
            "preferred_dates": None,
            "time_range": None,
            "constraints": [],
        }

        flexibility = agent._assess_flexibility(request)

        assert 0.0 <= flexibility <= 1.0
        assert flexibility >= 0.8

    def test_format_response_success(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test formatting successful scheduling result."""
        result = MagicMock(success=True, event_id="event_789")

        message = agent._format_response(result)

        assert "event_789" in message
        assert "successfully" in message.lower()

    def test_format_response_failure_with_conflicts(
        self, agent: SchedulingOrchestratorAgent
    ) -> None:
        """Test formatting failed scheduling result with conflict message."""
        result = MagicMock(
            success=False,
            conflicts=["3pm unavailable", "4pm has conflict"],
            message=None,
        )

        message = agent._format_response(result)

        assert "Could not schedule" in message

    def test_format_response_failure_no_slots(self, agent: SchedulingOrchestratorAgent) -> None:
        """Test formatting failed scheduling result with no slots."""
        result = MagicMock(
            success=False,
            message=None,
            conflicts=None,
        )

        message = agent._format_response(result)

        assert "Could not schedule" in message
        assert "No slots available" in message
