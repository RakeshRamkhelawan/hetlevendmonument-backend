"""
Tests for OODA-K Runtime Phase B3-B5 (Decision, Action, Knowledge Base).

Tests B3 (decide), B4 (act), and B5 (knowledge base integration).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.ooda_runtime import (
    ConfidenceLevel,
    DecisionMode,
    ExecutionResult,
    ObservationPhase,
    OODALoopExecutor,
    OrientationMode,
)
from src.core.shared.interfaces import TaskData


@pytest.fixture
def ooda_executor_with_kb():
    """Create OODA executor with knowledge base."""
    kb = {
        "agent_strategies": {"test-agent": {"preferred_mode": "staged", "retry_limit": 3}},
        "learned_patterns": {"high_complexity": {"success_rate": 0.85}},
    }
    return OODALoopExecutor(agent_id="test-agent", knowledge_base=kb)


class TestB3Decision:
    """Test Phase B3: Decide - action selection with confidence scoring."""

    @pytest.mark.asyncio
    async def test_decide_creates_context(self, ooda_executor_with_kb, sample_task):
        """B3: Decision should create valid decision context."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert decision is not None
        assert decision.orientation_analysis == orientation
        assert decision.timestamp is not None
        assert decision.decision_mode is not None

    @pytest.mark.asyncio
    async def test_decide_selects_best_option(self, ooda_executor_with_kb, sample_task):
        """B3: Should select option with highest confidence."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert decision.selected_action is not None
        assert decision.selected_action in [
            "direct_execution",
            "staged_execution",
            "fallback_simple",
        ]
        assert decision.selected_option_index >= 0

    @pytest.mark.asyncio
    async def test_decide_calculates_confidence(self, ooda_executor_with_kb, sample_task):
        """B3: Should calculate confidence score."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert 0.0 <= decision.confidence_score <= 1.0
        assert decision.confidence_score > 0  # Should be non-zero

    @pytest.mark.asyncio
    async def test_decide_assigns_confidence_level(self, ooda_executor_with_kb, sample_task):
        """B3: Should assign confidence level based on score."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        if decision.confidence_score < 0.33:
            assert decision.confidence_level == ConfidenceLevel.LOW
        elif decision.confidence_score < 0.66:
            assert decision.confidence_level == ConfidenceLevel.MEDIUM
        else:
            assert decision.confidence_level == ConfidenceLevel.HIGH

    @pytest.mark.asyncio
    async def test_decide_risk_assessment(self, ooda_executor_with_kb, sample_task):
        """B3: Should assess estimated risk."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert 0.0 <= decision.estimated_risk <= 1.0
        assert 0.0 <= decision.estimated_success_probability <= 1.0
        assert abs(decision.estimated_risk + decision.estimated_success_probability - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_decide_builds_rationale(self, ooda_executor_with_kb, sample_task):
        """B3: Should build decision rationale."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert decision.decision_rationale is not None
        assert len(decision.decision_rationale) > 0
        assert decision.selected_action in decision.decision_rationale

    @pytest.mark.asyncio
    async def test_decide_checks_preconditions(self, ooda_executor_with_kb, sample_task):
        """B3: Should check execution preconditions."""
        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        assert "has_time" in decision.preconditions_check
        assert "has_tools" in decision.preconditions_check
        assert "confidence_sufficient" in decision.preconditions_check
        assert isinstance(decision.preconditions_met, bool)

    @pytest.mark.asyncio
    async def test_decide_determines_decision_mode(self, ooda_executor_with_kb):
        """B3: Should determine decision mode based on constraints."""
        # Time critical task
        task = TaskData(
            title="Time Critical",
            description="Must complete quickly",
            agent_id="test-agent",
            tenant_id=1,
            execution_deadline=datetime.now(timezone.utc) + timedelta(seconds=3),
        )

        observation = await ooda_executor_with_kb.observe(task)
        orientation = await ooda_executor_with_kb.orient(observation)
        decision = await ooda_executor_with_kb.decide(orientation)

        # Time critical should be AUTONOMOUS
        assert decision.decision_mode == DecisionMode.AUTONOMOUS


class TestB4Action:
    """Test Phase B4: Act - tool execution with ReAct interleaving."""

    @pytest.mark.asyncio
    async def test_execute_ooda_cycle_basic(self, ooda_executor_with_kb, sample_task):
        """B4: Execute full OODA cycle."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id,
                success=True,
                output='{"result": "success"}',
                result_data={"result": "success"},
                error_message=None,
            )

        result = await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        assert result is not None
        assert result.success
        assert result.output is not None

    @pytest.mark.asyncio
    async def test_execute_ooda_cycle_records_execution(self, ooda_executor_with_kb, sample_task):
        """B4: Should record execution in history."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id,
                success=True,
                output="{}",
                result_data={},
                error_message=None,
            )

        initial_history_len = len(ooda_executor_with_kb.execution_history)

        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        assert len(ooda_executor_with_kb.execution_history) == initial_history_len + 1
        last_entry = ooda_executor_with_kb.execution_history[-1]
        assert last_entry["success"] is True

    @pytest.mark.asyncio
    async def test_execute_ooda_cycle_failure(self, ooda_executor_with_kb, sample_task):
        """B4: Should handle execution failure."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id,
                success=False,
                output=None,
                error_message="Execution failed",
            )

        result = await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        assert result.success is False
        assert result.error == "Execution failed"

        # Should be recorded as failure in history
        last_entry = ooda_executor_with_kb.execution_history[-1]
        assert last_entry["failed"] is True

    @pytest.mark.asyncio
    async def test_execute_ooda_cycle_precondition_failure(self, ooda_executor_with_kb):
        """B4: Should fail execution if preconditions not met."""
        # Create task with no time budget
        task = TaskData(
            title="No Time Task",
            description="Already expired",
            agent_id="test-agent",
            tenant_id=1,
            execution_deadline=datetime.now(timezone.utc) - timedelta(seconds=1),  # Already expired
        )

        async def mock_executor(decision_ctx):
            raise RuntimeError("Should not be called if preconditions fail")

        result = await ooda_executor_with_kb.execute_ooda_cycle(task, mock_executor)

        assert result.success is False
        assert "preconditions" in result.error.lower()

    @pytest.mark.asyncio
    async def test_ooda_cycle_creates_decision_trace(self, ooda_executor_with_kb, sample_task):
        """B4: Should create complete decision trace."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id,
                success=True,
                output="{}",
                result_data={},
                error_message=None,
            )

        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        # Execution history should contain the full trace
        history_entry = ooda_executor_with_kb.execution_history[-1]
        assert "task_id" in history_entry
        assert "decision" in history_entry
        assert "success" in history_entry
        assert "timestamp" in history_entry


class TestB5KnowledgeBase:
    """Test Phase B5: Knowledge Base - shared state for MAPE-K."""

    @pytest.mark.asyncio
    async def test_executor_initializes_with_kb(self):
        """B5: Executor should accept knowledge base."""
        kb = {"test": "data"}
        executor = OODALoopExecutor(agent_id="test-agent", knowledge_base=kb)

        assert executor.knowledge_base == kb

    @pytest.mark.asyncio
    async def test_executor_with_empty_kb(self):
        """B5: Executor should work with no KB."""
        executor = OODALoopExecutor(agent_id="test-agent")

        assert isinstance(executor.knowledge_base, dict)
        assert len(executor.knowledge_base) == 0

    @pytest.mark.asyncio
    async def test_executor_maintains_execution_history(self, ooda_executor_with_kb, sample_task):
        """B5: Knowledge base should track execution history."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id,
                success=True,
                output="{}",
                result_data={},
                error_message=None,
            )

        # Run multiple cycles
        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)
        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        assert len(ooda_executor_with_kb.execution_history) == 2

        # All entries should be properly formatted
        for entry in ooda_executor_with_kb.execution_history:
            assert "task_id" in entry
            assert "decision" in entry
            assert "success" in entry


class TestOODAIntegration:
    """Integration tests for full OODA-K runtime."""

    @pytest.mark.asyncio
    async def test_full_ooda_loop_from_task_to_result(self, ooda_executor_with_kb, sample_task):
        """Integration: Full OODA from task input to execution result."""

        async def mock_executor(decision_ctx):
            import json

            return ExecutionResult(
                task_id=sample_task.task_id,
                success=True,
                output=json.dumps({"executed_action": decision_ctx.selected_action}),
                result_data={"executed_action": decision_ctx.selected_action},
                error_message=None,
            )

        result = await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)

        # Should have complete result
        assert result.success
        assert result.result_data is not None
        assert "executed_action" in result.result_data

        # History should be updated
        history_entry = ooda_executor_with_kb.execution_history[-1]
        assert history_entry["task_id"] == sample_task.task_id

    @pytest.mark.asyncio
    async def test_ooda_with_repeated_failures_changes_strategy(
        self, ooda_executor_with_kb, sample_task
    ):
        """Integration: Should adapt strategy based on repeated failures."""
        # Fail twice
        ooda_executor_with_kb.execution_history = [{"failed": True}, {"failed": True}]

        observation = await ooda_executor_with_kb.observe(sample_task)
        orientation = await ooda_executor_with_kb.orient(observation)

        # Should detect constraint
        assert "repeated_failures" in orientation.key_constraints

        # Should have staged_execution as best option (more conservative)
        assert orientation.options_ranking[1]["option"] == "staged_execution"
        assert (
            orientation.options_ranking[1]["confidence"] > 0.8
        )  # High confidence in staged approach

    @pytest.mark.asyncio
    async def test_ooda_learnings_persist_across_cycles(self, ooda_executor_with_kb, sample_task):
        """Integration: Execution history should persist across cycles."""

        async def mock_executor(decision_ctx):
            return ExecutionResult(
                task_id=sample_task.task_id, success=True, output="{}", result_data={}, error=None
            )

        # Cycle 1
        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)
        assert len(ooda_executor_with_kb.execution_history) == 1

        # Cycle 2
        await ooda_executor_with_kb.execute_ooda_cycle(sample_task, mock_executor)
        assert len(ooda_executor_with_kb.execution_history) == 2

        # Both cycles should be retrievable
        task_executions = [
            e
            for e in ooda_executor_with_kb.execution_history
            if e["task_id"] == sample_task.task_id
        ]
        assert len(task_executions) == 2


@pytest.fixture
def sample_task():
    """Create a sample task."""
    return TaskData(
        title="Integration Test Task",
        description="Task for OODA integration testing",
        agent_id="test-agent",
        tenant_id=1,
        execution_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
