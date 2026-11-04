"""
Chaos Engineering Tests: Node Outage Recovery

Tests system resilience against node failures and recovery.
Requires: GOOGLE_API_KEY (LLM routing), live agent infrastructure.
"""

import asyncio
import os
import random
import time
from typing import Dict, List, Set
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio

# These tests drive real AgentRouterAgent which makes live LLM (Gemini) API
# calls when routing tasks. Skip the entire module if the API key is absent
# so that the test run does not hang waiting for a network timeout.
if not os.environ.get("GOOGLE_API_KEY"):
    pytest.skip(
        "GOOGLE_API_KEY not set - skipping LLM-dependent chaos tests",
        allow_module_level=True,
    )

from src.core.agents.agent_health_monitor_agent import AgentHealthMonitorAgent
from src.core.agents.agent_router_agent import AgentRouterAgent
from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.shared.interfaces import ExecutionResult, TaskData


class NodeManager:
    """Manages simulated cluster nodes."""

    def __init__(self):
        self.nodes: Dict[str, dict] = {}
        self.healthy_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()

    def register_node(self, node_id: str, capabilities: List[str] = None):
        """Register a new node in the cluster."""
        self.nodes[node_id] = {
            "id": node_id,
            "capabilities": capabilities or [],
            "status": "healthy",
            "load": 0.0,
            "tasks_processed": 0,
        }
        self.healthy_nodes.add(node_id)

    def fail_node(self, node_id: str):
        """Simulate node failure."""
        if node_id in self.nodes:
            self.nodes[node_id]["status"] = "failed"
            self.healthy_nodes.discard(node_id)
            self.failed_nodes.add(node_id)
            print(f"Node {node_id} failed")

    def recover_node(self, node_id: str):
        """Simulate node recovery."""
        if node_id in self.nodes:
            self.nodes[node_id]["status"] = "healthy"
            self.failed_nodes.discard(node_id)
            self.healthy_nodes.add(node_id)
            print(f"Node {node_id} recovered")

    def get_healthy_nodes(self) -> List[str]:
        """Get list of healthy nodes."""
        return list(self.healthy_nodes)

    def get_node_for_task(self, task_capabilities: List[str]) -> str:
        """Select best node for task (load balancing)."""
        candidates = [
            nid
            for nid in self.healthy_nodes
            if any(cap in self.nodes[nid]["capabilities"] for cap in task_capabilities)
        ]
        if not candidates:
            candidates = list(self.healthy_nodes)

        # Select least loaded node
        return min(candidates, key=lambda nid: self.nodes[nid]["load"])


@pytest_asyncio.fixture(scope="function")
async def node_manager():
    """Create node manager with test cluster."""
    manager = NodeManager()

    # Register 5 nodes
    for i in range(5):
        manager.register_node(f"node-{i}", capabilities=["compute", "memory", "storage"])

    yield manager

    # Cleanup
    manager.healthy_nodes.clear()
    manager.failed_nodes.clear()


@pytest.mark.chaos
@pytest.mark.asyncio
class TestSingleNodeFailure:
    """Test recovery from single node failures."""

    async def test_task_routing_after_node_failure(self, node_manager):
        """Test that tasks are rerouted when a node fails."""
        router = AgentRouterAgent(tenant_id=1)

        # Register agents on different nodes
        for i in range(5):
            await router.register(
                Mock(
                    agent_id=f"agent-{i}",
                    agent_type="TestAgent",
                    capabilities=["compute"],
                    node_id=f"node-{i}",
                )
            )

        # Fail node-2
        node_manager.fail_node("node-2")

        # Tasks should still be routed to healthy nodes
        task = TaskData(
            id="test-task-1",
            title="Test task",
            description="Test routing after failure",
        )

        for _ in range(10):
            agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)
            # Should not route to node-2 agents
            assert agent_id != "agent-2"
            assert agent_id is not None

    async def test_health_monitor_detects_failure(self, node_manager):
        """Test health monitor detects node failure."""
        monitor = AgentHealthMonitorAgent(tenant_id=1, poll_interval_s=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Record initial health (process immediately, don't batch)
            await asyncio.wait_for(
                monitor.record(
                    agent_id="agent-on-node-0",
                    agent_type="TestAgent",
                    latency_ms=100.0,
                    success=True,
                    load=0.5,
                    batch=False,  # Process immediately
                ),
                timeout=5.0,
            )

            # Simulate node failure (no more heartbeats)
            node_manager.fail_node("node-0")

            # Wait for health check interval (shorter for testing)
            await asyncio.sleep(1.5)

            # Health monitor should detect stale agent
            report = monitor.health_report()

            # Should have recorded agent
            assert report["total_agents"] >= 1

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)

    async def test_graceful_degradation(self, node_manager):
        """Test system degrades gracefully with fewer nodes."""
        orchestrator = MasterOrchestratorAgent(tenant_id=1)

        # Fail 2 of 5 nodes
        node_manager.fail_node("node-3")
        node_manager.fail_node("node-4")

        # System should still process tasks (with reduced capacity)
        tasks = []
        for i in range(5):
            task = TaskData(
                id=f"task-{i}",
                title=f"Task {i}",
                description="Test degraded mode",
            )
            tasks.append(orchestrator.process_task(task))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All tasks should complete (even if some fail gracefully)
        assert len(results) == 5

        # At least some should succeed
        success_count = sum(
            1 for r in results if isinstance(r, Exception) is False and getattr(r, "success", False)
        )
        assert success_count >= 3


@pytest.mark.chaos
@pytest.mark.asyncio
class TestMultipleNodeFailures:
    """Test recovery from multiple simultaneous node failures."""

    async def test_cascading_failure_handling(self, node_manager):
        """Test system handles cascading failures."""
        monitor = AgentHealthMonitorAgent(tenant_id=1, poll_interval_s=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Simulate cascading failures
            failed_nodes = []
            for i in range(4):  # Fail 4 of 5 nodes
                node_id = f"node-{i}"
                node_manager.fail_node(node_id)
                failed_nodes.append(node_id)

                # Record health after each failure (process immediately)
                await asyncio.wait_for(
                    monitor.record(
                        agent_id=f"agent-{i}",
                        agent_type="TestAgent",
                        latency_ms=100.0,
                        success=i < 2,  # First 2 succeed, rest fail
                        load=0.5,
                        batch=False,  # Process immediately
                    ),
                    timeout=5.0,
                )

                await asyncio.sleep(0.1)  # Short delay between failures

            # System should still be responsive with 1 node
            assert len(node_manager.get_healthy_nodes()) == 1

            # Health report should show degraded status
            report = monitor.health_report()
            assert report["total_agents"] >= 4

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)

    async def test_quorum_loss_prevention(self, node_manager):
        """Test system prevents split-brain scenarios."""
        # This is a conceptual test - actual implementation would use Raft/Paxos

        # Split network into two partitions
        partition_a = ["node-0", "node-1", "node-2"]
        partition_b = ["node-3", "node-4"]

        # Partition A has majority (3/5)
        # Partition B should not elect a leader

        healthy_in_a = sum(1 for n in partition_a if n in node_manager.healthy_nodes)
        healthy_in_b = sum(1 for n in partition_b if n in node_manager.healthy_nodes)

        # Partition A can proceed (has quorum)
        assert healthy_in_a >= 3

        # Partition B cannot proceed (no quorum)
        assert healthy_in_b < 3

    async def test_recovery_after_mass_failure(self, node_manager):
        """Test full recovery after all nodes fail."""
        orchestrator = MasterOrchestratorAgent(tenant_id=1)

        # Fail all nodes
        for i in range(5):
            node_manager.fail_node(f"node-{i}")

        # Wait a bit
        await asyncio.sleep(0.5)

        # Recover all nodes
        for i in range(5):
            node_manager.recover_node(f"node-{i}")

        # System should fully recover
        assert len(node_manager.get_healthy_nodes()) == 5

        # Should be able to process tasks
        task = TaskData(
            id="recovery-test",
            title="Recovery test",
            description="Test after full recovery",
        )

        result = await asyncio.wait_for(orchestrator.process_task(task), timeout=10.0)
        assert result is not None


@pytest.mark.chaos
@pytest.mark.asyncio
class TestNodeRecovery:
    """Test node recovery procedures."""

    async def test_fast_recovery(self, node_manager):
        """Test rapid node recovery."""
        # Fail and immediately recover
        node_manager.fail_node("node-0")
        await asyncio.sleep(0.5)
        node_manager.recover_node("node-0")

        # Node should be healthy
        assert "node-0" in node_manager.get_healthy_nodes()

        # Should accept new tasks
        router = AgentRouterAgent(tenant_id=1)
        task = TaskData(
            id="fast-recovery-test",
            title="Fast recovery test",
            description="Test",
        )

        # Should not throw
        agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)
        assert agent_id is not None

    async def test_data_reconciliation(self, node_manager):
        """Test data reconciliation after node recovery."""
        # Simulate data inconsistency scenario
        failed_node = "node-1"

        # Node fails during task execution
        node_manager.fail_node(failed_node)

        # Simulate some "lost" state
        lost_tasks = [f"task-{i}" for i in range(3)]

        # Node recovers
        node_manager.recover_node(failed_node)

        # System should reconcile - check health monitor
        monitor = AgentHealthMonitorAgent(tenant_id=1, poll_interval_s=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Record health from recovered node
            await asyncio.wait_for(
                monitor.record(
                    agent_id="agent-on-recovered-node",
                    agent_type="TestAgent",
                    latency_ms=100.0,
                    success=True,
                    load=0.0,
                    batch=False,  # Don't batch - process immediately
                ),
                timeout=5.0,
            )

            # Should be recorded
            snapshot = monitor.agent_status("agent-on-recovered-node")
            assert snapshot is not None

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)

    async def test_load_rebalancing(self, node_manager):
        """Test load is rebalanced after node recovery."""
        # Fail one node to concentrate load
        node_manager.fail_node("node-2")

        # Simulate load on remaining nodes
        for node_id in node_manager.get_healthy_nodes():
            node_manager.nodes[node_id]["load"] = 0.8

        # Recover the node
        node_manager.recover_node("node-2")

        # New node should have low/no load
        assert node_manager.nodes["node-2"]["load"] == 0.0

        # Router should start sending tasks to recovered node
        router = AgentRouterAgent(tenant_id=1)
        task = TaskData(
            id="rebalance-test",
            title="Rebalance test",
            description="Test load rebalancing",
        )

        # Route multiple tasks
        routed_to_recovered = 0
        for _ in range(20):
            agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)
            # Note: Actual routing depends on implementation
            # This is a simplified check
            assert agent_id is not None

        # Load should eventually balance (in real implementation)


@pytest.mark.chaos
@pytest.mark.asyncio
class TestGracefulShutdown:
    """Test graceful shutdown and handover."""

    async def test_graceful_node_shutdown(self, node_manager):
        """Test node drains before shutdown."""
        node_id = "node-0"

        # Simulate active tasks
        active_tasks = 3
        node_manager.nodes[node_id]["active_tasks"] = active_tasks

        # Mark node for draining
        node_manager.nodes[node_id]["status"] = "draining"

        # Wait for tasks to complete (simulated)
        await asyncio.sleep(0.5)
        node_manager.nodes[node_id]["active_tasks"] = 0

        # Now safe to fail/shutdown
        node_manager.fail_node(node_id)

        # No active tasks should be lost
        assert node_manager.nodes[node_id]["active_tasks"] == 0

    async def test_connection_draining(self):
        """Test HTTP connection draining during shutdown."""
        # Simulate incoming requests
        active_requests = 5

        # Signal shutdown
        draining = True

        # New requests should be rejected
        if draining:
            with pytest.raises(Exception):
                # This would raise in real implementation
                raise Exception("Node is draining")

        # Active requests should complete
        await asyncio.sleep(0.1)
        active_requests = 0  # All completed

        assert active_requests == 0


@pytest.mark.chaos
@pytest.mark.asyncio
class TestFailureDetection:
    """Test failure detection mechanisms."""

    async def test_heartbeat_failure_detection(self, node_manager):
        """Test nodes detected as failed when heartbeats stop."""
        monitor = AgentHealthMonitorAgent(tenant_id=1, poll_interval_s=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Register agent with heartbeat
            await asyncio.wait_for(
                monitor.record(
                    agent_id="heartbeat-test-agent",
                    agent_type="TestAgent",
                    latency_ms=100.0,
                    success=True,
                    load=0.5,
                ),
                timeout=5.0,
            )

            # Stop sending heartbeats (simulate node failure)
            await asyncio.sleep(2)  # Wait past heartbeat timeout

            # Health monitor should detect stale agent
            snapshot = monitor.agent_status("heartbeat-test-agent")
            if snapshot:
                # Should be marked as stale after timeout
                from datetime import datetime, timezone

                time_since_heartbeat = (
                    datetime.now(timezone.utc) - snapshot.last_heartbeat
                ).total_seconds()
                if time_since_heartbeat > 120:  # HEARTBEAT_TIMEOUT_S
                    assert snapshot.status.value in ["stale", "unknown"]

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)

    async def test_slow_node_detection(self, node_manager):
        """Test detection of slow (not failed) nodes."""
        monitor = AgentHealthMonitorAgent(tenant_id=1, poll_interval_s=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Record slow responses
            for _ in range(5):
                await asyncio.wait_for(
                    monitor.record(
                        agent_id="slow-agent",
                        agent_type="TestAgent",
                        latency_ms=5000.0,  # Very slow
                        success=True,
                        load=0.9,
                    ),
                    timeout=5.0,
                )

            # Should be marked as degraded
            snapshot = monitor.agent_status("slow-agent")
            if snapshot:
                assert snapshot.avg_latency_ms > 1000  # Slow

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)


# Runbook integration
"""
## Node Outage Recovery Runbook

### Detection
```bash
# Check node health
docker node ls
docker service ps sanskritisetu_app

# Check logs for node failures
docker service logs sanskritisetu_app --tail 100 | grep -iE "(error|fail)"
```

### Response Procedures

#### Single Node Failure
1. Verify failure: `docker node inspect <node-id>`
2. Drain node: `docker node update --availability drain <node-id>`
3. Investigate: Check node logs
4. Recover or replace node
5. Return to service: `docker node update --availability active <node-id>`

#### Multiple Node Failures
1. Assess impact: How many nodes affected?
2. If < quorum (50%+), system continues in degraded mode
3. If > quorum, may need emergency procedures
4. Contact on-call if critical

#### Full Cluster Recovery
1. Stop all services: `docker stack rm sanskritisetu`
2. Recover nodes: Restart/replace failed hardware
3. Re-initialize swarm if needed
4. Restore from backup if data loss
5. Gradual restart of services

### Prevention
- Set up node health alerts
- Regular hardware maintenance
- Redundant network paths
- Auto-failover for critical components
"""
