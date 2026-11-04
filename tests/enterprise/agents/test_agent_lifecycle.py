"""
Sprint E Tests - Agent Lifecycle & Health Monitoring

Tests for:
- Agent registration/deregistration
- Health monitoring and heartbeats
- Status transitions
- Capability tracking
- Resource monitoring
- Auto-cleanup of offline agents
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core.als.enterprise.agents.agent_lifecycle import (
    AgentCapabilities,
    AgentHealth,
    AgentLifecycleManager,
    AgentStatus,
    AgentType,
    create_agent_capabilities,
)


class TestAgentRegistration:
    """Test agent registration and deregistration."""

    @pytest.fixture
    async def lifecycle(self):
        """Create lifecycle manager."""
        manager = AgentLifecycleManager()
        await manager.start()
        yield manager
        await manager.stop()

    @pytest.mark.asyncio
    async def test_register_agent_success(self, lifecycle):
        """Can register a new agent."""
        result = await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
            skills=["budget_analysis"],
            technologies=["ml"],
        )

        assert result is True
        assert "agent_1" in lifecycle.get_all_agents(1)

    @pytest.mark.asyncio
    async def test_register_duplicate_fails(self, lifecycle):
        """Cannot register duplicate agent."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        result = await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_unregister_agent(self, lifecycle):
        """Can unregister an agent."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        result = await lifecycle.unregister_agent("agent_1", 1)

        assert result is True
        assert "agent_1" not in lifecycle.get_all_agents(1)

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_fails(self, lifecycle):
        """Unregistering non-existent agent returns False."""
        result = await lifecycle.unregister_agent("nonexistent", 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_agent_capabilities(self, lifecycle):
        """Can retrieve agent capabilities."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
            skills=["budget_analysis", "forecasting"],
            technologies=["ml", "llm"],
            max_concurrent_tasks=3,
        )

        caps = lifecycle.get_agent_capabilities("agent_1", 1)

        assert caps is not None
        assert caps.agent_id == "agent_1"
        assert caps.department == "finance"
        assert "budget_analysis" in caps.skills
        assert caps.max_concurrent_tasks == 3

    @pytest.mark.asyncio
    async def test_get_agent_health(self, lifecycle):
        """Can retrieve agent health."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        health = lifecycle.get_agent_health("agent_1", 1)

        assert health is not None
        assert health.agent_id == "agent_1"
        assert health.status == AgentStatus.IDLE
        assert health.health_score == 100


class TestAgentHeartbeat:
    """Test heartbeat and health monitoring."""

    @pytest.fixture
    async def lifecycle(self):
        """Create lifecycle manager."""
        manager = AgentLifecycleManager()
        await manager.start()
        yield manager
        await manager.stop()

    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self, lifecycle):
        """Heartbeat updates last_heartbeat."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        old_health = lifecycle.get_agent_health("agent_1", 1)
        old_timestamp = old_health.last_heartbeat

        await asyncio.sleep(0.1)

        result = await lifecycle.heartbeat("agent_1", 1)
        assert result is True

        new_health = lifecycle.get_agent_health("agent_1", 1)
        assert new_health.last_heartbeat > old_timestamp

    @pytest.mark.asyncio
    async def test_heartbeat_updates_status(self, lifecycle):
        """Heartbeat can update agent status."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        await lifecycle.heartbeat("agent_1", 1, status=AgentStatus.BUSY)

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.status == AgentStatus.BUSY

    @pytest.mark.asyncio
    async def test_heartbeat_updates_health_metrics(self, lifecycle):
        """Heartbeat updates health metrics."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        await lifecycle.heartbeat(
            "agent_1",
            1,
            health_metrics={
                "cpu_percent": 75.0,
                "memory_percent": 60.0,
                "prana_available": 500,
            },
        )

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.cpu_percent == 75.0
        assert health.memory_percent == 60.0
        assert health.prana_available == 500

    @pytest.mark.asyncio
    async def test_heartbeat_brings_offline_back(self, lifecycle):
        """Heartbeat from OFFLINE agent marks as IDLE."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        # Simulate offline
        health = lifecycle.get_agent_health("agent_1", 1)
        health.status = AgentStatus.OFFLINE

        # Heartbeat without status should bring back to IDLE
        await lifecycle.heartbeat("agent_1", 1)

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.status == AgentStatus.IDLE


class TestAgentHealthMonitoring:
    """Test health monitoring and auto-cleanup."""

    @pytest.mark.asyncio
    async def test_offline_detection(self):
        """Agents without heartbeat are marked OFFLINE."""
        manager = AgentLifecycleManager()
        manager.HEARTBEAT_TIMEOUT_SECONDS = 0.1  # Short timeout for test
        await manager.start()

        try:
            await manager.register_agent(
                agent_id="agent_1",
                agent_type=AgentType.SPECIALIST,
                department="finance",
                tenant_id=1,
            )

            # Wait for heartbeat timeout
            await asyncio.sleep(0.3)

            # Trigger health check
            await manager._check_all_agents()

            health = manager.get_agent_health("agent_1", 1)
            assert health.status == AgentStatus.OFFLINE
            assert health.health_score == 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_auto_unregister_after_extended_offline(self):
        """Agents offline too long are auto-unregistered."""
        manager = AgentLifecycleManager()
        manager.HEARTBEAT_TIMEOUT_SECONDS = 0.05
        manager.MAX_OFFLINE_TIME_SECONDS = 0.1
        await manager.start()

        try:
            await manager.register_agent(
                agent_id="agent_1",
                agent_type=AgentType.SPECIALIST,
                department="finance",
                tenant_id=1,
            )

            # Wait for auto-cleanup
            await asyncio.sleep(0.3)
            await manager._check_all_agents()

            assert "agent_1" not in manager.get_all_agents(1)
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_health_score_calculation(self):
        """Health score is calculated from metrics."""
        manager = AgentLifecycleManager()
        await manager.start()

        try:
            await manager.register_agent(
                agent_id="agent_1",
                agent_type=AgentType.SPECIALIST,
                department="finance",
                tenant_id=1,
            )

            # High resource usage should reduce score
            await manager.heartbeat(
                "agent_1",
                1,
                health_metrics={
                    "cpu_percent": 90.0,  # > 80, -20
                    "memory_percent": 85.0,  # > 80, -20
                },
            )

            health = manager.get_agent_health("agent_1", 1)
            assert health.health_score <= 60  # 100 - 20 - 20
        finally:
            await manager.stop()


class TestAgentStatus:
    """Test agent status methods."""

    def test_is_healthy(self):
        """is_healthy returns True for IDLE and BUSY."""
        idle_health = AgentHealth(
            agent_id="a1",
            status=AgentStatus.IDLE,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
        )
        assert idle_health.is_healthy() is True

        busy_health = AgentHealth(
            agent_id="a1",
            status=AgentStatus.BUSY,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
        )
        assert busy_health.is_healthy() is True

        offline_health = AgentHealth(
            agent_id="a1",
            status=AgentStatus.OFFLINE,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
        )
        assert offline_health.is_healthy() is False

    def test_is_available_for_work(self):
        """is_available_for_work requires IDLE and health_score >= 50."""
        available = AgentHealth(
            agent_id="a1",
            status=AgentStatus.IDLE,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            health_score=75,
        )
        assert available.is_available_for_work() is True

        busy = AgentHealth(
            agent_id="a1",
            status=AgentStatus.BUSY,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            health_score=75,
        )
        assert busy.is_available_for_work() is False

        degraded = AgentHealth(
            agent_id="a1",
            status=AgentStatus.IDLE,
            registered_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
            health_score=30,  # < 50
        )
        assert degraded.is_available_for_work() is False


class TestDepartmentQueries:
    """Test department-based agent queries."""

    @pytest.fixture
    async def lifecycle_with_agents(self):
        """Create lifecycle with multiple agents."""
        manager = AgentLifecycleManager()
        await manager.start()

        # Finance agents
        await manager.register_agent(
            agent_id="finance_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
            skills=["budget_analysis"],
        )
        await manager.register_agent(
            agent_id="finance_2",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
            skills=["forecasting"],
        )

        # HR agents
        await manager.register_agent(
            agent_id="hr_1",
            agent_type=AgentType.SPECIALIST,
            department="hr",
            tenant_id=1,
            skills=["hiring"],
        )

        yield manager
        await manager.stop()

    @pytest.mark.asyncio
    async def test_get_agents_by_department(self, lifecycle_with_agents):
        """Can get agents by department."""
        finance_agents = lifecycle_with_agents.get_agents_by_department("finance", 1)

        assert "finance_1" in finance_agents
        assert "finance_2" in finance_agents
        assert "hr_1" not in finance_agents

    @pytest.mark.asyncio
    async def test_get_agents_by_capability(self, lifecycle_with_agents):
        """Can get agents by capability."""
        budget_agents = lifecycle_with_agents.get_agents_by_capability("budget_analysis", 1)

        assert "finance_1" in budget_agents
        assert "finance_2" not in budget_agents

    @pytest.mark.asyncio
    async def test_get_healthy_agents_only(self, lifecycle_with_agents):
        """Can filter by healthy status."""
        # Mark one agent as offline
        await lifecycle_with_agents.heartbeat("finance_1", 1, status=AgentStatus.OFFLINE)

        healthy_agents = lifecycle_with_agents.get_agents_by_department(
            "finance", 1, healthy_only=True
        )

        assert "finance_1" not in healthy_agents
        assert "finance_2" in healthy_agents

    @pytest.mark.asyncio
    async def test_get_available_agents_only(self, lifecycle_with_agents):
        """Can filter by available status."""
        # Mark one agent as busy
        await lifecycle_with_agents.heartbeat("finance_1", 1, status=AgentStatus.BUSY)

        available_agents = lifecycle_with_agents.get_agents_by_capability(
            "budget_analysis", 1, available_only=True
        )

        assert "finance_1" not in available_agents  # BUSY, not available

    @pytest.mark.asyncio
    async def test_department_health_summary(self, lifecycle_with_agents):
        """Can get department health summary."""
        summary = lifecycle_with_agents.get_department_health_summary("finance", 1)

        assert summary["department"] == "finance"
        assert summary["total_agents"] == 2
        assert summary["healthy"] == 2


class TestTaskMetrics:
    """Test task completion metrics."""

    @pytest.fixture
    async def lifecycle(self):
        """Create lifecycle manager."""
        manager = AgentLifecycleManager()
        await manager.start()
        await manager.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )
        yield manager
        await manager.stop()

    @pytest.mark.asyncio
    async def test_update_task_success(self, lifecycle):
        """Successful task updates metrics."""
        await lifecycle.update_task_metrics("agent_1", 1, 1000.0, success=True)

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.tasks_completed == 1
        assert health.tasks_failed == 0
        assert health.avg_task_duration_ms == 1000.0

    @pytest.mark.asyncio
    async def test_update_task_failure(self, lifecycle):
        """Failed task updates metrics."""
        await lifecycle.update_task_metrics("agent_1", 1, 500.0, success=False)

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.tasks_completed == 0
        assert health.tasks_failed == 1

    @pytest.mark.asyncio
    async def test_average_duration_calculation(self, lifecycle):
        """Average duration is calculated correctly."""
        await lifecycle.update_task_metrics("agent_1", 1, 1000.0, success=True)
        await lifecycle.update_task_metrics("agent_1", 1, 2000.0, success=True)

        health = lifecycle.get_agent_health("agent_1", 1)
        assert health.avg_task_duration_ms == 1500.0


class TestTenantIsolation:
    """Test tenant isolation in agent management."""

    @pytest.fixture
    async def lifecycle(self):
        """Create lifecycle manager."""
        manager = AgentLifecycleManager()
        await manager.start()
        yield manager
        await manager.stop()

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, lifecycle):
        """Agents are isolated by tenant."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )
        await lifecycle.register_agent(
            agent_id="agent_1",  # Same ID, different tenant
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=2,
        )

        agents_t1 = lifecycle.get_all_agents(1)
        agents_t2 = lifecycle.get_all_agents(2)

        assert "agent_1" in agents_t1
        assert "agent_1" in agents_t2

        # Unregister from tenant 1 only
        await lifecycle.unregister_agent("agent_1", 1)

        assert "agent_1" not in lifecycle.get_all_agents(1)
        assert "agent_1" in lifecycle.get_all_agents(2)

    @pytest.mark.asyncio
    async def test_get_health_wrong_tenant(self, lifecycle):
        """Cannot get health from wrong tenant."""
        await lifecycle.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.SPECIALIST,
            department="finance",
            tenant_id=1,
        )

        health = lifecycle.get_agent_health("agent_1", 2)  # Wrong tenant
        assert health is None


class TestMetrics:
    """Test lifecycle metrics."""

    @pytest.mark.asyncio
    async def test_registration_metrics(self):
        """Metrics track registrations."""
        manager = AgentLifecycleManager()
        await manager.start()

        try:
            await manager.register_agent(
                agent_id="agent_1",
                agent_type=AgentType.SPECIALIST,
                department="finance",
                tenant_id=1,
            )
            await manager.register_agent(
                agent_id="agent_2",
                agent_type=AgentType.SPECIALIST,
                department="finance",
                tenant_id=1,
            )
            await manager.unregister_agent("agent_1", 1)

            metrics = manager.get_metrics()
            assert metrics["registered"] == 2
            assert metrics["deregistered"] == 1
        finally:
            await manager.stop()


class TestCreateAgentCapabilities:
    """Test convenience function."""

    def test_create_capabilities(self):
        """Can create capabilities with helper."""
        caps = create_agent_capabilities(
            agent_id="test_agent",
            department="finance",
            tenant_id=1,
            skills=["budget", "forecast"],
            agent_type=AgentType.SPECIALIST,
            technologies=["ml", "llm"],
        )

        assert caps.agent_id == "test_agent"
        assert caps.department == "finance"
        assert caps.tenant_id == 1
        assert "budget" in caps.skills
        assert caps.agent_type == AgentType.SPECIALIST
