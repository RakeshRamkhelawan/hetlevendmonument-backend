"""
Tests for OODA-K Runtime Implementation (Phase B).

Tests B1 (observe) and B2 (orient) phases of the OODA control loop.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.agents.ooda_runtime import (
    ConfidenceLevel,
    DecisionContext,
    DecisionMode,
    ObservationPhase,
    ObservationSnapshot,
    OODALoopExecutor,
    OrientationAnalysis,
    OrientationMode,
    SensorReading,
)
from src.core.shared.interfaces import ExecutionResult, TaskData


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return TaskData(
        title="Test Task",
        description="Test task for OODA runtime testing",
        agent_id="test-agent",
        tenant_id=1,
        metadata={"query": "test query"},
        execution_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


@pytest.fixture
def ooda_executor():
    """Create an OODA loop executor."""
    return OODALoopExecutor(agent_id="test-agent")


class TestB1Observation:
    """Test Phase B1: Observe - sensor aggregation."""

    @pytest.mark.asyncio
    async def test_observe_creates_snapshot(self, ooda_executor, sample_task):
        """B1: Observation should create valid snapshot."""
        snapshot = await ooda_executor.observe(sample_task)

        assert snapshot is not None
        assert snapshot.agent_id == "test-agent"
        assert snapshot.task_id == sample_task.task_id  # Use the actual task_id
        assert snapshot.phase == ObservationPhase.INITIAL
        assert snapshot.timestamp is not None

    @pytest.mark.asyncio
    async def test_observe_collects_all_sensors(self, ooda_executor, sample_task):
        """B1: Observation should collect readings from all sensors."""
        snapshot = await ooda_executor.observe(sample_task)

        # Should have readings from: task_complexity, available_tools, time_budget, prior_failures, metadata_size
        assert len(snapshot.readings) >= 5
        assert "task_complexity" in snapshot.readings
        assert "available_tools_count" in snapshot.readings
        assert "time_budget_remaining_seconds" in snapshot.readings
        assert "prior_failure_count" in snapshot.readings
        assert "metadata_keys_count" in snapshot.readings

    @pytest.mark.asyncio
    async def test_observe_calculates_task_complexity(self, ooda_executor, sample_task):
        """B1: Task complexity should be calculated correctly."""
        snapshot = await ooda_executor.observe(sample_task)

        assert 0.0 <= snapshot.task_complexity <= 1.0
        assert snapshot.task_complexity > 0  # Should be non-zero for non-empty task

    @pytest.mark.asyncio
    async def test_observe_detects_available_tools(self, ooda_executor, sample_task):
        """B1: Available tools should be detected from task."""
        sample_task.metadata["tools"] = ["tool1", "tool2", "tool3"]
        snapshot = await ooda_executor.observe(sample_task)

        assert snapshot.available_tools == ["tool1", "tool2", "tool3"]
        assert len(snapshot.available_tools) == 3

    @pytest.mark.asyncio
    async def test_observe_calculates_time_budget(self, ooda_executor, sample_task):
        """B1: Time budget should be calculated from execution deadline."""
        snapshot = await ooda_executor.observe(sample_task)

        assert snapshot.time_budget_remaining.total_seconds() > 0
        assert snapshot.time_budget_remaining.total_seconds() <= 300  # 5 minutes max

    @pytest.mark.asyncio
    async def test_observe_tracks_prior_failures(self, ooda_executor, sample_task):
        """B1: Prior failures should be tracked from execution history."""
        # Initially should be 0
        snapshot1 = await ooda_executor.observe(sample_task)
        assert snapshot1.prior_failures == 0

        # Add failure to history
        ooda_executor.execution_history.append({"failed": True})
        snapshot2 = await ooda_executor.observe(sample_task)
        assert snapshot2.prior_failures == 1

    @pytest.mark.asyncio
    async def test_observe_sensor_reliability(self, ooda_executor, sample_task):
        """B1: Sensor readings should have reliability scores."""
        snapshot = await ooda_executor.observe(sample_task)

        for reading in snapshot.readings.values():
            assert 0.0 <= reading.reliability <= 1.0
            assert reading.sensor_type is not None
            assert reading.reading_name is not None

    @pytest.mark.asyncio
    async def test_observe_average_reliability(self, ooda_executor, sample_task):
        """B1: Average reliability should be computed correctly."""
        snapshot = await ooda_executor.observe(sample_task)
        avg_reliability = snapshot.average_reliability()

        assert 0.0 <= avg_reliability <= 1.0
        assert avg_reliability > 0.9  # Should be high for typical task

    @pytest.mark.asyncio
    async def test_observe_different_phases(self, ooda_executor, sample_task):
        """B1: Observation should support different phases."""
        snapshot_initial = await ooda_executor.observe(sample_task, ObservationPhase.INITIAL)
        assert snapshot_initial.phase == ObservationPhase.INITIAL

        snapshot_intermediate = await ooda_executor.observe(
            sample_task, ObservationPhase.INTERMEDIATE
        )
        assert snapshot_intermediate.phase == ObservationPhase.INTERMEDIATE

        snapshot_final = await ooda_executor.observe(sample_task, ObservationPhase.FINAL)
        assert snapshot_final.phase == ObservationPhase.FINAL

    @pytest.mark.asyncio
    async def test_observe_snapshot_to_dict(self, ooda_executor, sample_task):
        """B1: Observation snapshot should convert to dict for LLM reasoning."""
        snapshot = await ooda_executor.observe(sample_task)
        snapshot_dict = snapshot.to_dict()

        assert "phase" in snapshot_dict
        assert "agent_id" in snapshot_dict
        assert "task_id" in snapshot_dict
        assert "task_complexity" in snapshot_dict
        assert "available_tools" in snapshot_dict
        assert "time_budget_remaining_seconds" in snapshot_dict


class TestB2Orientation:
    """Test Phase B2: Orient - situational analysis."""

    @pytest.mark.asyncio
    async def test_orient_creates_analysis(self, ooda_executor, sample_task):
        """B2: Orientation should create valid analysis."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        assert analysis is not None
        assert analysis.observation_snapshot == observation
        assert analysis.orientation_mode == OrientationMode.HYBRID
        assert analysis.timestamp is not None

    @pytest.mark.asyncio
    async def test_orient_builds_reasoning_trace(self, ooda_executor, sample_task):
        """B2: Orientation should build reasoning trace."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        assert len(analysis.reasoning_trace) > 0
        assert any("complexity" in trace.lower() for trace in analysis.reasoning_trace)
        assert any("tools" in trace.lower() for trace in analysis.reasoning_trace)

    @pytest.mark.asyncio
    async def test_orient_detects_constraints(self, ooda_executor, sample_task):
        """B2: Orientation should detect key constraints."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        # With normal task, should not have major constraints
        # But the analysis should have constraint detection logic
        assert analysis.key_constraints is not None
        assert isinstance(analysis.key_constraints, list)

    @pytest.mark.asyncio
    async def test_orient_detects_repeated_failures_constraint(self, ooda_executor, sample_task):
        """B2: Should detect repeated_failures constraint."""
        # Add failures to history
        ooda_executor.execution_history = [{"failed": True}, {"failed": True}, {"failed": True}]

        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        assert "repeated_failures" in analysis.key_constraints
        assert "needs_fresh_approach" in analysis.key_constraints

    @pytest.mark.asyncio
    async def test_orient_detects_time_critical_constraint(self, ooda_executor):
        """B2: Should detect time_critical constraint."""
        task = TaskData(
            title="Time Critical Task",
            description="Must complete within 5 seconds",
            agent_id="test-agent",
            tenant_id=1,
            execution_deadline=datetime.now(timezone.utc) + timedelta(seconds=5),  # Only 5 seconds
        )

        observation = await ooda_executor.observe(task)
        analysis = await ooda_executor.orient(observation)

        assert "time_critical" in analysis.key_constraints

    @pytest.mark.asyncio
    async def test_orient_detects_high_complexity_constraint(self, ooda_executor):
        """B2: Should detect high_complexity constraint."""
        # Create task with EXTREMELY large description to trigger high_complexity
        task = TaskData(
            title="VeryComplexTask" + "x" * 300,
            description="x" * 20000,  # Very large description (exceeds 500*0.3 threshold)
            agent_id="test-agent",
            tenant_id=1,
            metadata={f"k{i}": f"v{i}" for i in range(100)},  # Large metadata
            tags=[f"tag{i}" for i in range(20)],
            execution_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        observation = await ooda_executor.observe(task)
        analysis = await ooda_executor.orient(observation)

        # High complexity should be detected
        assert observation.task_complexity > 0.5
        assert "high_complexity" in analysis.key_constraints

    @pytest.mark.asyncio
    async def test_orient_identifies_risks(self, ooda_executor):
        """B2: Orientation should identify risks."""
        ooda_executor.execution_history = [{"failed": True}]

        task = TaskData(
            title="Risky Task",
            description="A task with prior failures",
            agent_id="test-agent",
            tenant_id=1,
            execution_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        observation = await ooda_executor.observe(task)
        analysis = await ooda_executor.orient(observation)

        assert len(analysis.risks) > 0
        risk_descriptions = [r[0] for r in analysis.risks]
        assert "Repeated failure" in risk_descriptions

    @pytest.mark.asyncio
    async def test_orient_ranks_options(self, ooda_executor, sample_task):
        """B2: Orientation should rank action options."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        assert len(analysis.options_ranking) > 0
        assert all("option" in opt for opt in analysis.options_ranking)
        assert all("confidence" in opt for opt in analysis.options_ranking)
        assert all("risk" in opt for opt in analysis.options_ranking)

    @pytest.mark.asyncio
    async def test_orient_situation_assessment(self, ooda_executor, sample_task):
        """B2: Orientation should produce situation assessment."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        assert analysis.situation_assessment is not None
        assert len(analysis.situation_assessment) > 0
        assert "complexity" in analysis.situation_assessment.lower()
        assert "failures" in analysis.situation_assessment.lower()

    @pytest.mark.asyncio
    async def test_orient_different_modes(self, ooda_executor, sample_task):
        """B2: Orientation should support different modes."""
        observation = await ooda_executor.observe(sample_task)

        analysis_analytical = await ooda_executor.orient(observation, OrientationMode.ANALYTICAL)
        assert analysis_analytical.orientation_mode == OrientationMode.ANALYTICAL

        analysis_hybrid = await ooda_executor.orient(observation, OrientationMode.HYBRID)
        assert analysis_hybrid.orientation_mode == OrientationMode.HYBRID

    @pytest.mark.asyncio
    async def test_orient_analysis_to_dict(self, ooda_executor, sample_task):
        """B2: Analysis should convert to dict for decision."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)
        analysis_dict = analysis.to_dict()

        assert "situation_assessment" in analysis_dict
        assert "key_constraints" in analysis_dict
        assert "risks" in analysis_dict
        assert "opportunities" in analysis_dict
        assert "options_ranking" in analysis_dict


class TestB1B2Integration:
    """Integration tests for B1 and B2 together."""

    @pytest.mark.asyncio
    async def test_observation_flows_to_orientation(self, ooda_executor, sample_task):
        """B1→B2: Observation should flow correctly to orientation."""
        observation = await ooda_executor.observe(sample_task)
        analysis = await ooda_executor.orient(observation)

        # Analysis should reference the observation
        assert analysis.observation_snapshot == observation
        # Should have derived constraints from observation
        assert len(analysis.reasoning_trace) > 0

    @pytest.mark.asyncio
    async def test_complexity_flows_from_observation(self, ooda_executor):
        """B1→B2: Task complexity from observation should influence orientation."""
        complex_task = TaskData(
            title="VeryComplexTask" + "x" * 200,
            description="x" * 10000,
            agent_id="test-agent",
            tenant_id=1,
            metadata={f"k{i}": f"v{i}" for i in range(200)},
            tags=[f"tag{i}" for i in range(30)],
            execution_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        observation = await ooda_executor.observe(complex_task)
        analysis = await ooda_executor.orient(observation)

        # High complexity should be detected
        assert observation.task_complexity > 0.5
        assert "high_complexity" in analysis.key_constraints

    @pytest.mark.asyncio
    async def test_full_observation_orientation_cycle(self, ooda_executor, sample_task):
        """B1→B2: Full cycle from observation to orientation."""
        observation = await ooda_executor.observe(sample_task, ObservationPhase.INITIAL)
        assert observation.agent_id == "test-agent"
        assert len(observation.readings) > 0

        analysis = await ooda_executor.orient(observation)
        assert len(analysis.reasoning_trace) > 0
        assert len(analysis.options_ranking) > 0

        # Analysis should be internally consistent
        for option in analysis.options_ranking:
            assert 0.0 <= option["confidence"] <= 1.0
            assert 0.0 <= option["risk"] <= 1.0
