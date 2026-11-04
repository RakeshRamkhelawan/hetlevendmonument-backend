"""Unit tests for Swarm Orchestrator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.als.swarm.swarm_orchestrator import Swarm, SwarmMember, SwarmOrchestrator, SwarmRole
from src.core.als.swarm.task_decomposer import TaskDecomposer
from src.core.shared.interfaces import ExecutionResult, TaskData

# ==================== SWARM MEMBER TESTS ====================


class TestSwarmMemberHappyPaths:
    """Test SwarmMember basic functionality."""

    def test_member_creation(self):
        """Test creating a swarm member."""
        member = SwarmMember(
            agent_id="agent_001",
            role=SwarmRole.EXECUTOR,
            capabilities=["coding", "testing"],
        )

        assert member.agent_id == "agent_001"
        assert member.role == SwarmRole.EXECUTOR
        assert member.capabilities == ["coding", "testing"]
        assert member.status == "idle"
        assert member.assigned_tasks == []
        assert member.completed_tasks == 0
        assert member.joined_at is not None

    def test_member_to_dict(self):
        """Test member serialization."""
        member = SwarmMember("agent_001", SwarmRole.LEADER, ["planning"])
        member.assigned_tasks = ["task_1"]
        member.completed_tasks = 2

        data = member.to_dict()

        assert data["agent_id"] == "agent_001"
        assert data["role"] == "leader"
        assert data["capabilities"] == ["planning"]
        assert data["status"] == "idle"
        assert data["assigned_tasks"] == ["task_1"]
        assert data["completed_tasks"] == 2
        assert "joined_at" in data


class TestSwarmMemberRoles:
    """Test SwarmRole enum."""

    def test_role_values(self):
        """Test role enum values."""
        assert SwarmRole.LEADER == "leader"
        assert SwarmRole.STRATEGIST == "strategist"
        assert SwarmRole.EXECUTOR == "executor"
        assert SwarmRole.REVIEWER == "reviewer"
        assert SwarmRole.SPECIALIST == "specialist"
        assert SwarmRole.SUPPORT == "support"

    def test_role_in_member(self):
        """Test role assignment in member."""
        leader = SwarmMember("a1", SwarmRole.LEADER)
        strategist = SwarmMember("a2", SwarmRole.STRATEGIST)
        executor = SwarmMember("a3", SwarmRole.EXECUTOR)

        assert leader.role == SwarmRole.LEADER
        assert strategist.role == SwarmRole.STRATEGIST
        assert executor.role == SwarmRole.EXECUTOR


# ==================== SWARM TESTS ====================


class TestSwarmHappyPaths:
    """Test Swarm basic functionality."""

    def test_swarm_creation(self):
        """Test creating a swarm."""
        swarm = Swarm(
            tenant_id=123,
            mission="Refactor authentication",
            required_capabilities=["security", "coding"],
            max_size=4,
        )

        assert swarm.tenant_id == 123
        assert swarm.mission == "Refactor authentication"
        assert swarm.required_capabilities == ["security", "coding"]
        assert swarm.max_size == 4
        assert swarm.size == 0
        assert swarm.status == "forming"
        assert swarm.swarm_id is not None
        assert swarm.created_at is not None

    def test_add_member(self):
        """Test adding members to swarm."""
        swarm = Swarm(1, "Test", ["coding"], max_size=3)

        result = swarm.add_member("agent_1", SwarmRole.LEADER, ["planning"])

        assert result is True
        assert swarm.size == 1
        assert "agent_1" in swarm.members
        assert swarm.members["agent_1"].role == SwarmRole.LEADER

    def test_add_multiple_members(self):
        """Test adding multiple members."""
        swarm = Swarm(1, "Test", ["coding", "testing"], max_size=3)

        swarm.add_member("agent_1", SwarmRole.LEADER)
        swarm.add_member("agent_2", SwarmRole.EXECUTOR)
        swarm.add_member("agent_3", SwarmRole.REVIEWER)

        assert swarm.size == 3
        assert swarm.is_full is True

    def test_assign_task(self):
        """Test task assignment."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR)

        result = swarm.assign_task("task_001", "agent_1")

        assert result is True
        member = swarm.members["agent_1"]
        assert "task_001" in member.assigned_tasks
        assert member.status == "working"

    def test_complete_task_success(self):
        """Test successful task completion."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR)
        swarm.assign_task("task_001", "agent_1")

        result = swarm.complete_task("task_001", success=True)

        assert result is True
        member = swarm.members["agent_1"]
        assert member.completed_tasks == 1
        assert member.status == "completed"

    def test_activate_swarm(self):
        """Test swarm activation."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR)

        swarm.activate()

        assert swarm.status == "active"
        assert swarm.activated_at is not None
        assert swarm.leader is not None  # Auto-assigned

    def test_swarm_to_dict(self):
        """Test swarm serialization."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER, ["planning"])

        data = swarm.to_dict()

        assert data["swarm_id"] == swarm.swarm_id
        assert data["tenant_id"] == 1
        assert data["mission"] == "Test"
        assert data["size"] == 1
        assert data["status"] == "forming"
        assert "members" in data
        assert "capability_coverage" in data

    def test_capability_coverage(self):
        """Test capability coverage calculation."""
        swarm = Swarm(1, "Test", ["coding", "testing", "security"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR, ["coding"])
        swarm.add_member("agent_2", SwarmRole.REVIEWER, ["testing"])

        coverage = swarm.get_capabilities_coverage()

        assert coverage["coding"] is True
        assert coverage["testing"] is True
        assert coverage["security"] is False
        assert swarm.capability_coverage_ratio == 2 / 3


class TestSwarmStatusTransitions:
    """Test swarm status transitions."""

    def test_form_to_active_transition(self):
        """Test forming -> active transition."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER)

        assert swarm.status == "forming"
        swarm.activate()
        assert swarm.status == "active"

    def test_active_to_completed_transition(self):
        """Test active -> completed transition."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER)
        swarm.activate()

        # Create a simple ExecutionResult mock
        result = ExecutionResult(
            task_id="task_001",
            success=True,
            output="Test completed",
            metrics={"duration_ms": 100},
        )
        swarm.complete(result)

        assert swarm.status == "completed"
        assert swarm.completed_at is not None
        assert swarm.results is not None

    def test_dissolve_swarm(self):
        """Test swarm dissolution."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER)

        swarm.dissolve()

        assert swarm.status == "dissolved"
        assert swarm.completed_at is not None


class TestSwarmUnhappyPaths:
    """Test Swarm error handling."""

    def test_add_member_to_full_swarm(self):
        """Test adding member when swarm is full."""
        swarm = Swarm(1, "Test", ["coding"], max_size=2)
        swarm.add_member("agent_1", SwarmRole.LEADER)
        swarm.add_member("agent_2", SwarmRole.EXECUTOR)

        result = swarm.add_member("agent_3", SwarmRole.SUPPORT)

        assert result is False
        assert swarm.size == 2

    def test_add_duplicate_member(self):
        """Test adding same agent twice."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER)

        result = swarm.add_member("agent_1", SwarmRole.EXECUTOR)

        assert result is False
        assert swarm.size == 1

    def test_activate_empty_swarm(self):
        """Test activating empty swarm fails."""
        swarm = Swarm(1, "Test", ["coding"])

        with pytest.raises(ValueError):
            swarm.activate()

    def test_assign_task_to_nonexistent_agent(self):
        """Test assigning task to agent not in swarm."""
        swarm = Swarm(1, "Test", ["coding"])

        result = swarm.assign_task("task_001", "agent_1")

        assert result is False

    def test_complete_nonexistent_task(self):
        """Test completing task that wasn't assigned."""
        swarm = Swarm(1, "Test", ["coding"])

        result = swarm.complete_task("task_999")

        assert result is False

    def test_remove_member(self):
        """Test removing a member."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.LEADER)

        result = swarm.remove_member("agent_1")

        assert result is True
        assert swarm.size == 0

    def test_remove_nonexistent_member(self):
        """Test removing agent not in swarm."""
        swarm = Swarm(1, "Test", ["coding"])

        result = swarm.remove_member("agent_1")

        assert result is False


# ==================== SWARM ORCHESTRATOR TESTS ====================


class TestSwarmOrchestratorHappyPaths:
    """Test SwarmOrchestrator basic functionality."""

    @pytest.fixture
    def orchestrator(self):
        return SwarmOrchestrator(tenant_id=123)

    @pytest.mark.asyncio
    async def test_orchestrator_creation(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator.tenant_id == 123
        assert orchestrator._swarms == {}
        assert orchestrator._agent_swarm_map == {}

    @pytest.mark.asyncio
    async def test_form_swarm(self, orchestrator):
        """Test forming a new swarm."""
        swarm = await orchestrator.form_swarm(
            mission="Test mission",
            required_capabilities=["coding", "testing"],
            available_agents=["agent_1", "agent_2", "agent_3"],
            agent_capabilities={
                "agent_1": ["coding"],
                "agent_2": ["testing"],
                "agent_3": ["coding", "testing"],
            },
            min_size=2,
            max_size=3,
        )

        assert swarm is not None
        assert swarm.mission == "Test mission"
        assert swarm.tenant_id == 123
        assert swarm.size >= 2
        assert swarm.swarm_id in orchestrator._swarms

    @pytest.mark.asyncio
    async def test_activate_swarm(self, orchestrator):
        """Test swarm activation."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )

        result = await orchestrator.activate_swarm(swarm.swarm_id)

        assert result is True
        assert swarm.status == "active"

    @pytest.mark.asyncio
    async def test_get_swarm_status(self, orchestrator):
        """Test getting swarm status."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )

        status = orchestrator.get_swarm_status(swarm.swarm_id)

        assert status is not None
        assert status["swarm_id"] == swarm.swarm_id
        assert status["mission"] == "Test"

    @pytest.mark.asyncio
    async def test_get_active_swarms(self, orchestrator):
        """Test listing active swarms."""
        await orchestrator.form_swarm(
            mission="Test 1",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )
        await orchestrator.form_swarm(
            mission="Test 2",
            required_capabilities=["testing"],
            available_agents=["agent_2"],
            agent_capabilities={"agent_2": ["testing"]},
            min_size=1,
            max_size=2,
        )

        active = orchestrator.get_active_swarms()

        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_get_swarm_for_agent(self, orchestrator):
        """Test finding swarm for an agent."""
        await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )

        swarm_id = orchestrator.get_swarm_for_agent("agent_1")

        assert swarm_id is not None

    @pytest.mark.asyncio
    async def test_assign_task_to_swarm(self, orchestrator):
        """Test task assignment through orchestrator."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )
        await orchestrator.activate_swarm(swarm.swarm_id)

        task = TaskData(
            id="task_001",
            title="Test task",
            description="A test task",
        )

        agent_id = await orchestrator.assign_task_to_swarm(swarm.swarm_id, task)

        assert agent_id == "agent_1"
        assert orchestrator.get_agent_workload("agent_1") == 1

    @pytest.mark.asyncio
    async def test_complete_task(self, orchestrator):
        """Test task completion."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )
        await orchestrator.activate_swarm(swarm.swarm_id)

        task = TaskData(id="task_001", title="Test", description="Test task")
        await orchestrator.assign_task_to_swarm(swarm.swarm_id, task)

        result = await orchestrator.complete_task(swarm.swarm_id, "task_001")

        assert result is True

    @pytest.mark.asyncio
    async def test_complete_swarm(self, orchestrator):
        """Test completing a swarm mission."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )
        await orchestrator.activate_swarm(swarm.swarm_id)

        result = ExecutionResult(
            task_id="swarm_mission_001",
            success=True,
            output="Swarm mission completed",
            metrics={"tasks_completed": 5},
        )
        completed = await orchestrator.complete_swarm(swarm.swarm_id, result)

        assert completed is True
        assert swarm.status == "completed"
        assert orchestrator.get_swarm_for_agent("agent_1") is None  # Cleaned up

    @pytest.mark.asyncio
    async def test_dissolve_swarm(self, orchestrator):
        """Test swarm dissolution."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )

        dissolved = await orchestrator.dissolve_swarm(swarm.swarm_id)

        assert dissolved is True
        assert swarm.status == "dissolved"

    def test_get_orchestrator_stats(self, orchestrator):
        """Test getting orchestrator statistics."""
        stats = orchestrator.get_orchestrator_stats()

        assert stats["total_swarms"] == 0
        assert stats["active_swarms"] == 0
        assert stats["agents_in_swarms"] == 0
        assert "swarm_status_distribution" in stats


class TestSwarmOrchestratorSwarmFormation:
    """Test swarm formation logic."""

    @pytest.fixture
    def orchestrator(self):
        return SwarmOrchestrator(tenant_id=123)

    @pytest.mark.asyncio
    async def test_form_swarm_not_enough_agents(self, orchestrator):
        """Test swarm formation with insufficient agents."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],  # Only 1 agent
            agent_capabilities={"agent_1": ["coding"]},
            min_size=3,  # But need 3
            max_size=5,
        )

        assert swarm is None

    @pytest.mark.asyncio
    async def test_form_swarm_role_assignment(self, orchestrator):
        """Test that roles are assigned correctly."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding", "testing"],
            available_agents=["agent_1", "agent_2", "agent_3"],
            agent_capabilities={
                "agent_1": ["planning", "coding"],
                "agent_2": ["testing"],
                "agent_3": ["review", "coding"],
            },
            min_size=2,
            max_size=4,
        )

        assert swarm is not None
        assert swarm.leader is not None  # First agent becomes leader
        assert swarm.size >= 2

    @pytest.mark.asyncio
    async def test_form_swarm_capability_coverage(self, orchestrator):
        """Test swarm selects agents covering required capabilities."""
        swarm = await orchestrator.form_swarm(
            mission="Complex task",
            required_capabilities=["coding", "testing", "security"],
            available_agents=["agent_1", "agent_2", "agent_3", "agent_4"],
            agent_capabilities={
                "agent_1": ["coding"],
                "agent_2": ["testing"],
                "agent_3": ["security"],
                "agent_4": ["coding"],  # Redundant
            },
            min_size=2,
            max_size=4,
        )

        assert swarm is not None
        coverage = swarm.get_capabilities_coverage()
        assert coverage["coding"] is True
        assert coverage["testing"] is True
        assert coverage["security"] is True


class TestSwarmOrchestratorUnhappyPaths:
    """Test orchestrator error handling."""

    @pytest.fixture
    def orchestrator(self):
        return SwarmOrchestrator(tenant_id=123)

    @pytest.mark.asyncio
    async def test_activate_nonexistent_swarm(self, orchestrator):
        """Test activating non-existent swarm."""
        result = await orchestrator.activate_swarm("nonexistent_id")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_swarm_status_nonexistent(self, orchestrator):
        """Test getting status of non-existent swarm."""
        status = orchestrator.get_swarm_status("nonexistent_id")

        assert status is None

    @pytest.mark.asyncio
    async def test_assign_task_to_inactive_swarm(self, orchestrator):
        """Test assigning task to swarm that isn't active."""
        swarm = await orchestrator.form_swarm(
            mission="Test",
            required_capabilities=["coding"],
            available_agents=["agent_1"],
            agent_capabilities={"agent_1": ["coding"]},
            min_size=1,
            max_size=2,
        )
        # Don't activate - swarm is still "forming"

        task = TaskData(id="task_001", title="Test", description="Test task")
        agent_id = await orchestrator.assign_task_to_swarm(swarm.swarm_id, task)

        assert agent_id is None

    @pytest.mark.asyncio
    async def test_complete_nonexistent_swarm(self, orchestrator):
        """Test completing non-existent swarm."""
        result = ExecutionResult(task_id="test_task", success=True, output="Test", metrics={})
        completed = await orchestrator.complete_swarm("nonexistent_id", result)

        assert completed is False

    @pytest.mark.asyncio
    async def test_dissolve_nonexistent_swarm(self, orchestrator):
        """Test dissolving non-existent swarm."""
        dissolved = await orchestrator.dissolve_swarm("nonexistent_id")

        assert dissolved is False


# ==================== TASK DECOMPOSER TESTS ====================


class TestTaskDecomposerHappyPaths:
    """Test TaskDecomposer functionality."""

    @pytest.fixture
    def decomposer(self):
        return TaskDecomposer()

    def test_estimate_complexity_simple_task(self, decomposer):
        """Test complexity estimation for simple task."""
        task = TaskData(
            id="task_1",
            title="Simple fix",
            description="Fix typo",
        )

        estimate = decomposer.estimate_complexity(task)

        assert estimate["complexity_score"] <= 5
        assert estimate["recommended_swarm_size"] <= 3
        assert estimate["parallelizable"] is False

    def test_estimate_complexity_complex_task(self, decomposer):
        """Test complexity estimation for complex task."""
        task = TaskData(
            id="task_1",
            title="Large migration",
            description="A" * 600,  # Long description
            tags=["complex", "critical"],
        )

        estimate = decomposer.estimate_complexity(task)

        assert estimate["complexity_score"] > 5
        assert estimate["recommended_swarm_size"] >= 3

    def test_decompose_refactoring_task(self, decomposer):
        """Test decomposing refactoring task."""
        task = TaskData(
            id="task_1",
            title="Refactor auth module",
            description="Clean up auth",
        )

        subtasks = decomposer.decompose(
            task=task,
            swarm_capabilities=["architecture", "coding", "testing"],
        )

        assert len(subtasks) > 0
        assert all("title" in st for st in subtasks)
        assert all("required_capabilities" in st for st in subtasks)

    def test_decompose_security_task(self, decomposer):
        """Test decomposing security audit task."""
        task = TaskData(
            id="task_1",
            title="Security audit",
            description="Check vulnerabilities",
        )

        subtasks = decomposer.decompose(
            task=task,
            swarm_capabilities=["security", "analysis"],
        )

        assert len(subtasks) > 0
        # Should include scanning, review, report
        titles = [st["title"].lower() for st in subtasks]
        assert any("scan" in t or "review" in t for t in titles)

    def test_decompose_performance_task(self, decomposer):
        """Test decomposing performance optimization task."""
        task = TaskData(
            id="task_1",
            title="Optimize database",
            description="Improve query performance",
        )

        subtasks = decomposer.decompose(
            task=task,
            swarm_capabilities=["performance", "profiling", "coding"],
        )

        assert len(subtasks) > 0
        titles = [st["title"].lower() for st in subtasks]
        assert any("profil" in t or "benchmark" in t or "optimization" in t for t in titles)


class TestTaskDecomposerLimits:
    """Test decomposer limits."""

    @pytest.fixture
    def decomposer(self):
        return TaskDecomposer()

    def test_decompose_respects_max_subtasks(self, decomposer):
        """Test that decomposer respects max_subtasks limit."""
        task = TaskData(
            id="task_1",
            title="Refactor everything",
            description="Major refactoring",
        )

        subtasks = decomposer.decompose(
            task=task,
            swarm_capabilities=["coding"],
            max_subtasks=3,
        )

        assert len(subtasks) <= 3

    def test_decompose_dependencies_valid(self, decomposer):
        """Test that dependencies reference valid subtasks."""
        task = TaskData(
            id="task_1",
            title="Test task",
            description="Test",
        )

        subtasks = decomposer.decompose(
            task=task,
            swarm_capabilities=["coding"],
        )

        for i, subtask in enumerate(subtasks):
            if "depends_on" in subtask:
                for dep in subtask["depends_on"]:
                    assert 0 <= dep < len(subtasks)
                    assert dep != i  # No self-dependencies


# ==================== INTEGRATION HELPERS ====================


class TestSwarmIntegrationHelpers:
    """Test helper methods and utilities."""

    def test_swarm_member_default_capabilities(self):
        """Test member with no capabilities provided."""
        member = SwarmMember("agent_1", SwarmRole.SUPPORT)
        assert member.capabilities == []

    def test_swarm_is_full_property(self):
        """Test is_full property."""
        swarm = Swarm(1, "Test", ["coding"], max_size=2)

        assert not swarm.is_full

        swarm.add_member("agent_1", SwarmRole.LEADER)
        assert not swarm.is_full

        swarm.add_member("agent_2", SwarmRole.EXECUTOR)
        assert swarm.is_full

    def test_swarm_leader_assignment(self):
        """Test leader auto-assignment on activation."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR)  # Not leader initially

        swarm.activate()

        assert swarm.leader is not None
        assert swarm.leader.agent_id == "agent_1"

    def test_swarm_active_members(self):
        """Test active_members property."""
        swarm = Swarm(1, "Test", ["coding"])
        swarm.add_member("agent_1", SwarmRole.EXECUTOR)
        swarm.add_member("agent_2", SwarmRole.SUPPORT)

        swarm.assign_task("task_1", "agent_1")

        active = swarm.active_members
        assert len(active) == 1
        assert active[0].agent_id == "agent_1"

    def test_swarm_empty_coverage(self):
        """Test capability coverage with empty requirements."""
        swarm = Swarm(1, "Test", required_capabilities=[], max_size=3)
        swarm.add_member("agent_1", SwarmRole.LEADER)

        coverage = swarm.get_capabilities_coverage()
        assert coverage == {}
        assert swarm.capability_coverage_ratio == 1.0

    @pytest.mark.asyncio
    async def test_orchestrator_agent_not_in_swarm(self):
        """Test workload for agent not in any swarm."""
        orchestrator = SwarmOrchestrator(1)

        workload = orchestrator.get_agent_workload("agent_1")

        assert workload == 0
