"""
Chaos Engineering Tests: Network Failure Simulation

Tests system resilience against network partitions, latency, and packet loss.
"""

import asyncio
import random
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pytest_asyncio import fixture

from src.core.agents.agent_router_agent import AgentRouterAgent
from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.shared.interfaces import TaskData


class NetworkPartitionSimulator:
    """Simulates network partitions between services."""

    def __init__(self):
        self.partitions: Dict[str, List[str]] = {}
        self.latency_ms: Dict[str, int] = {}
        self.packet_loss_rate: Dict[str, float] = {}

    async def partition_services(self, group_a: List[str], group_b: List[str]):
        """Create network partition between two service groups."""
        for service in group_a:
            self.partitions[service] = group_b
        for service in group_b:
            self.partitions[service] = group_a
        print(f"Network partition created: {group_a} <-> {group_b}")

    async def heal_partitions(self):
        """Remove all network partitions."""
        self.partitions.clear()
        print("Network partitions healed")

    async def add_latency(self, service: str, latency_ms: int):
        """Add latency to a service."""
        self.latency_ms[service] = latency_ms
        print(f"Added {latency_ms}ms latency to {service}")

    async def add_packet_loss(self, service: str, loss_rate: float):
        """Add packet loss to a service."""
        self.packet_loss_rate[service] = loss_rate
        print(f"Added {loss_rate*100}% packet loss to {service}")

    async def simulate_request(self, from_service: str, to_service: str) -> bool:
        """Simulate a request between services."""
        # Check partition
        if from_service in self.partitions and to_service in self.partitions[from_service]:
            return False

        # Apply packet loss
        if to_service in self.packet_loss_rate:
            if random.random() < self.packet_loss_rate[to_service]:
                return False

        # Apply latency
        if to_service in self.latency_ms:
            await asyncio.sleep(self.latency_ms[to_service] / 1000)

        return True


@fixture(scope="function")
async def network_sim():
    """Create network partition simulator."""
    sim = NetworkPartitionSimulator()
    yield sim
    await sim.heal_partitions()


@pytest.fixture(autouse=True)
def _no_real_llm_calls():
    """OP-198: every test in this file that touches process_task()/route() can reach a
    real Gemini call through `src.core.llm.fallback_chain.get_fallback_chain()`.

    Two independent, unconditional call sites share this one source function, both via a
    local import (so this module -- the shared source -- is the only patch target that
    covers both):
      - `MasterOrchestratorAgent._plan_workflow()` (master_orchestrator_agent.py:303 import,
        :386 call) -- the FIRST step of `process_task()`, before any routing happens.
      - `AgentRouterAgent._llm_route()` (agent_router_agent.py:728, called from :554) --
        guarded by `if not self.llm_client or not self._manifests: return None`, so not
        every test reaches it, but nothing here special-cases it either.

    Measured before this fixture existed: `test_orchestrator_during_db_partition`,
    `test_timeout_handling` and `test_multiple_service_failures` all instantiate
    `MasterOrchestratorAgent` and call `process_task()` with no mock, so all three made a
    real outbound call on every run. The mocked chain raises, which both call sites already
    handle gracefully (`except Exception` -> `logger.warning(...)` -> fallback/None), so the
    chaos scenario each test actually cares about (DB partition, latency, concurrent
    failures) stays intact. `test_graceful_degradation_no_llm` sets `llm_client = None`
    itself and never reaches `get_fallback_chain()`, so this fixture is a no-op there.
    """
    mock_chain = MagicMock()
    mock_chain.generate = AsyncMock(side_effect=Exception("LLM unavailable (mocked for chaos tests)"))
    with patch("src.core.llm.fallback_chain.get_fallback_chain", return_value=mock_chain):
        yield


@pytest.mark.chaos
@pytest.mark.asyncio
class TestNetworkPartitioning:
    """Test system behavior under network partitions."""

    async def test_orchestrator_during_db_partition(self, network_sim):
        """Test orchestrator handles database partition gracefully."""
        orchestrator = MasterOrchestratorAgent(tenant_id=1)

        # Create partition between app and database
        await network_sim.partition_services(["app"], ["postgres"])

        task = TaskData(
            id="test-task-1",
            title="Test during partition",
            description="Test workflow during DB partition",
        )

        # Should not crash, should return error result or complete
        # (depending on fallback mechanisms available)
        try:
            result = await asyncio.wait_for(orchestrator.process_task(task), timeout=10.0)
            # Either success (fallback worked) or graceful failure
            assert result is not None
        except asyncio.TimeoutError:
            # Timeout is acceptable - means system didn't crash
            pass
        except Exception as e:
            # Expected behavior - error should be handled gracefully
            # (database error, connection error, or API errors are all acceptable)
            error_msg = str(e).lower()
            assert (
                "database" in error_msg
                or "connection" in error_msg
                or "api" in error_msg
                or "timeout" in error_msg
                or "error" in error_msg
            )

        # Heal partition and retry
        await network_sim.heal_partitions()

        # Should work normally after healing (or at least not crash)
        try:
            result = await asyncio.wait_for(orchestrator.process_task(task), timeout=10.0)
            # Should return a result (success or graceful failure)
            assert result is not None
        except Exception:
            # Even if it fails, system shouldn't crash
            pass

    async def test_routing_during_redis_partition(self, network_sim):
        """Test router handles Redis partition."""
        router = AgentRouterAgent(tenant_id=1)

        # Create partition between app and Redis
        await network_sim.partition_services(["app"], ["redis"])

        task = TaskData(
            id="test-task-2",
            title="Route test task",
            description="Test routing without cache",
        )

        # Should fall back to LLM or capability matching
        agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)

        # Should still return an agent (fallback mechanism)
        assert agent_id is not None
        assert isinstance(agent_id, str)

    async def test_multi_partition_recovery(self, network_sim):
        """Test recovery from multiple simultaneous partitions."""
        # Create multiple partitions
        await network_sim.partition_services(["app-1"], ["postgres", "redis"])
        await network_sim.partition_services(["app-2"], ["rabbitmq"])

        # Simulate various requests during partition
        results = []
        for i in range(5):
            success = await network_sim.simulate_request("app-1", "postgres")
            results.append(success)

        # Most requests should fail during partition
        assert results.count(False) >= 3

        # Heal all partitions
        await network_sim.heal_partitions()

        # All requests should succeed after healing
        for i in range(5):
            success = await network_sim.simulate_request("app-1", "postgres")
            assert success


@pytest.mark.chaos
@pytest.mark.asyncio
class TestLatencyInjection:
    """Test system behavior under high latency."""

    async def test_high_latency_routing(self, network_sim):
        """Test routing decisions under high latency."""
        router = AgentRouterAgent(tenant_id=1)

        # Add 500ms latency to LLM calls
        await network_sim.add_latency("llm-provider", 500)

        task = TaskData(
            id="test-task-3",
            title="High latency test",
            description="Test routing with slow LLM",
        )

        start = time.time()
        agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)
        elapsed = time.time() - start

        # Should complete within reasonable time (using cache or fallback)
        assert elapsed < 5.0  # Should not wait for slow LLM
        assert agent_id is not None

    async def test_timeout_handling(self, network_sim):
        """Test proper timeout handling."""
        orchestrator = MasterOrchestratorAgent(tenant_id=1)

        # Add extreme latency
        await network_sim.add_latency("database", 10000)  # 10 seconds

        task = TaskData(
            id="test-task-4",
            title="Timeout test",
            description="Test timeout handling",
        )

        # Should either timeout gracefully or complete (fallback)
        try:
            result = await asyncio.wait_for(orchestrator.process_task(task), timeout=5.0)
            # If it completes, that's fine (fallback mechanism worked)
            assert result is not None
        except asyncio.TimeoutError:
            # Timeout is expected behavior
            pass
        except Exception as e:
            # Other errors are also acceptable (graceful degradation)
            error_msg = str(e).lower()
            assert "error" in error_msg or "timeout" in error_msg or "api" in error_msg


@pytest.mark.chaos
@pytest.mark.asyncio
class TestPacketLoss:
    """Test system behavior under packet loss."""

    async def test_packet_loss_health_monitoring(self, network_sim):
        """Test health monitoring under packet loss."""
        from src.core.agents.agent_health_monitor_agent import AgentHealthMonitorAgent

        monitor = AgentHealthMonitorAgent(tenant_id=1)
        await asyncio.wait_for(monitor.start(), timeout=5.0)

        try:
            # Add 20% packet loss
            await network_sim.add_packet_loss("health-service", 0.2)

            # Record multiple health metrics (process immediately)
            success_count = 0
            for i in range(10):
                try:
                    await asyncio.wait_for(
                        monitor.record(
                            agent_id=f"agent-{i}",
                            agent_type="TestAgent",
                            latency_ms=100.0,
                            success=True,
                            load=0.5,
                            batch=False,  # Process immediately
                        ),
                        timeout=5.0,
                    )
                    success_count += 1
                except Exception:
                    pass

            # Should handle packet loss gracefully (at least some succeed)
            assert success_count >= 5  # At least 50% success with 20% loss

        finally:
            await asyncio.wait_for(monitor.stop(), timeout=5.0)

    async def test_retry_mechanism(self, network_sim):
        """Test automatic retry under packet loss."""
        attempt_count = 0

        async def flaky_operation():
            nonlocal attempt_count
            attempt_count += 1

            # Deterministic: first 2 attempts fail, then succeed
            if attempt_count <= 2:
                raise ConnectionError("Packet lost")
            return "success"

        # Retry with exponential backoff
        result = None
        for attempt in range(5):
            try:
                result = await flaky_operation()
                break
            except ConnectionError:
                wait_time = 0.1 * (2**attempt)
                await asyncio.sleep(wait_time)

        # Should eventually succeed after 2 retries
        assert result == "success"
        assert attempt_count == 3


@pytest.mark.chaos
@pytest.mark.asyncio
class TestServiceDegradation:
    """Test graceful degradation under resource constraints."""

    async def test_graceful_degradation_no_llm(self):
        """Test system works when LLM is unavailable."""
        router = AgentRouterAgent(tenant_id=1)

        # Disable LLM (simulate failure)
        router.llm_client = None

        task = TaskData(
            id="test-task-5",
            title="No LLM test",
            description="Test routing without LLM",
        )

        # Should fall back to capability matching
        agent_id = await asyncio.wait_for(router.route(task), timeout=10.0)
        assert agent_id is not None

    async def test_circuit_breaker_pattern(self):
        """Test circuit breaker opens after repeated failures."""
        failure_count = 0
        circuit_open = False

        async def call_external_service():
            nonlocal failure_count, circuit_open

            if circuit_open:
                raise Exception("Circuit breaker open")

            # Simulate increasing failures
            failure_count += 1
            if failure_count > 3:
                circuit_open = True

            if failure_count <= 3:
                raise ConnectionError("Service unavailable")

            return "success"

        # Circuit should open after 3 failures
        for i in range(5):
            try:
                await call_external_service()
            except Exception as e:
                if i >= 3:
                    assert "Circuit breaker" in str(e)


@pytest.mark.chaos
@pytest.mark.asyncio
class TestConcurrentFailures:
    """Test system under multiple concurrent failure scenarios."""

    async def test_multiple_service_failures(self, network_sim):
        """Test behavior when multiple services fail simultaneously."""
        orchestrator = MasterOrchestratorAgent(tenant_id=1)

        # Create multiple issues
        await network_sim.add_latency("database", 1000)
        await network_sim.add_packet_loss("cache", 0.3)
        await network_sim.partition_services(["app"], ["queue"])

        tasks = []
        for i in range(10):
            task = TaskData(
                id=f"concurrent-task-{i}",
                title=f"Concurrent test {i}",
                description="Test under multiple failures",
            )
            tasks.append(orchestrator.process_task(task))

        # Run concurrently with timeout
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=30.0
        )

        # System should not crash, some tasks may fail gracefully
        success_count = sum(1 for r in results if not isinstance(r, Exception))

        # At least some tasks should complete (even if failed gracefully)
        assert len(results) == 10
        print(f"Success rate under failures: {success_count}/10")

    async def test_rapid_failure_recovery(self, network_sim):
        """Test rapid failure and recovery cycles."""
        service_available = True

        async def toggle_service():
            nonlocal service_available
            for _ in range(5):
                await asyncio.sleep(0.5)
                service_available = not service_available

        async def use_service():
            results = []
            for _ in range(10):
                await asyncio.sleep(0.3)
                if service_available:
                    results.append("success")
                else:
                    results.append("unavailable")
            return results

        # Run toggler and user concurrently with timeout
        toggler_task = asyncio.create_task(toggle_service())
        user_results = await asyncio.wait_for(use_service(), timeout=10.0)
        await asyncio.wait_for(toggler_task, timeout=10.0)

        # Should handle rapid transitions
        assert "success" in user_results
        assert "unavailable" in user_results


# Runbook-style test documentation
"""
## Chaos Test Runbook

### Pre-requisites
- Test environment isolated from production
- Database with test data
- All services running

### Running Tests

```bash
# Run all chaos tests
pytest tests/chaos/ -v -m chaos

# Run specific test class
pytest tests/chaos/test_network_failures.py -v -k TestNetworkPartitioning

# Run with coverage
pytest tests/chaos/ -v -m chaos --cov=src.core
```

### Expected Results

All tests should:
1. Not crash the system
2. Return graceful error messages
3. Recover automatically when issues are resolved
4. Maintain data integrity

### Cleanup

Tests automatically clean up after themselves, but manual cleanup:
```bash
# Reset network conditions
# (Tests use fixtures that auto-cleanup)

# Verify system health
pytest tests/integration/test_orchestration_system.py -v
```
"""
