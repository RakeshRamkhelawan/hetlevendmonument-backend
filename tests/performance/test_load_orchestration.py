"""
Load Testing: Orchestration System Performance

Tests system behavior under high concurrent load.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List

import pytest
import pytest_asyncio
from httpx import AsyncClient


@dataclass
class LoadTestResult:
    """Results from a load test run."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    requests_per_second: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    percentile_95: float
    percentile_99: float
    errors: Dict[str, int] = field(default_factory=dict)


class LoadTester:
    """Load testing utility."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = AsyncClient(base_url=base_url, timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def make_request(self, endpoint: str, data: dict = None) -> tuple:
        """Make a single request and return timing."""
        start = time.time()
        try:
            if data:
                response = await self.client.post(endpoint, json=data)
            else:
                response = await self.client.get(endpoint)

            elapsed = time.time() - start
            return response.status_code == 200, elapsed, None
        except Exception as e:
            elapsed = time.time() - start
            return False, elapsed, str(e)

    async def run_load_test(
        self,
        endpoint: str,
        data: dict = None,
        concurrent_users: int = 100,
        requests_per_user: int = 10,
    ) -> LoadTestResult:
        """Run load test with specified concurrency."""

        results = []
        errors = {}

        async def user_session():
            """Simulate a user session making multiple requests."""
            for _ in range(requests_per_user):
                success, elapsed, error = await self.make_request(endpoint, data)
                results.append((success, elapsed))
                if error:
                    errors[error] = errors.get(error, 0) + 1

                # Small delay between requests (think time)
                await asyncio.sleep(0.1)

        start_time = time.time()

        # Create concurrent user sessions
        tasks = [user_session() for _ in range(concurrent_users)]
        await asyncio.gather(*tasks)

        total_time = time.time() - start_time

        # Calculate statistics
        successful = sum(1 for s, _ in results if s)
        failed = len(results) - successful
        response_times = [t for _, t in results]

        response_times.sort()
        n = len(response_times)

        return LoadTestResult(
            total_requests=len(results),
            successful_requests=successful,
            failed_requests=failed,
            total_time=total_time,
            requests_per_second=len(results) / total_time,
            avg_response_time=sum(response_times) / len(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            percentile_95=response_times[int(n * 0.95)] if n > 0 else 0,
            percentile_99=response_times[int(n * 0.99)] if n > 0 else 0,
            errors=errors,
        )


@pytest_asyncio.fixture
async def load_tester():
    """Create load tester."""
    tester = LoadTester()
    yield tester
    await tester.close()


@pytest.mark.performance
@pytest.mark.asyncio
class TestOrchestrationLoad:
    """Load tests for orchestration endpoints."""

    @pytest.mark.skip(reason="Performance tests require running server")
    async def test_health_endpoint_load(self, load_tester):
        """Test health endpoint under load."""
        result = await load_tester.run_load_test(
            endpoint="/health",
            concurrent_users=50,
            requests_per_user=20,
        )

        print("\nHealth Endpoint Load Test Results:")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Success Rate: {result.successful_requests / result.total_requests * 100:.1f}%")
        print(f"  RPS: {result.requests_per_second:.1f}")
        print(f"  Avg Response: {result.avg_response_time * 1000:.1f}ms")
        print(f"  P95: {result.percentile_95 * 1000:.1f}ms")
        print(f"  P99: {result.percentile_99 * 1000:.1f}ms")

        # Assertions
        assert result.successful_requests / result.total_requests > 0.99  # 99% success
        assert result.avg_response_time < 0.5  # < 500ms average
        assert result.percentile_95 < 1.0  # < 1s for 95th percentile

    @pytest.mark.skip(reason="Performance tests require running server")
    async def test_route_endpoint_load(self, load_tester):
        """Test routing endpoint under load."""
        route_data = {
            "task": {
                "title": "Load test task",
                "description": "Test routing under load",
            },
            "required_capabilities": [],
            "fallback_to_llm": False,
        }

        result = await load_tester.run_load_test(
            endpoint="/api/v1/orchestrate/route",
            data=route_data,
            concurrent_users=100,
            requests_per_user=5,
        )

        print("\nRoute Endpoint Load Test Results:")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Success Rate: {result.successful_requests / result.total_requests * 100:.1f}%")
        print(f"  RPS: {result.requests_per_second:.1f}")
        print(f"  Avg Response: {result.avg_response_time * 1000:.1f}ms")

        # Routing should be fast (cache-based)
        assert result.successful_requests / result.total_requests > 0.95
        assert result.avg_response_time < 1.0
        assert result.percentile_95 < 2.0

    @pytest.mark.skip(reason="Performance tests require running server")
    async def test_concurrent_workflow_submissions(self, load_tester):
        """Test concurrent workflow submissions."""
        workflow_data = {
            "task": {
                "title": "Concurrent workflow test",
                "description": "Test workflow orchestration under load",
            },
            "workflow_mode": "sequential",
            "max_subtasks": 4,
        }

        result = await load_tester.run_load_test(
            endpoint="/api/v1/orchestrate/task",
            data=workflow_data,
            concurrent_users=20,  # Lower concurrent users for workflows
            requests_per_user=3,
        )

        print("\nWorkflow Submission Load Test Results:")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Success Rate: {result.successful_requests / result.total_requests * 100:.1f}%")
        print(f"  RPS: {result.requests_per_second:.1f}")
        print(f"  Avg Response: {result.avg_response_time * 1000:.1f}ms")

        # Workflows take longer but should still succeed
        assert result.successful_requests / result.total_requests > 0.90
        assert result.avg_response_time < 10.0  # < 10s for workflow creation

    @pytest.mark.skip(reason="Performance tests require running server")
    async def test_health_monitor_load(self, load_tester):
        """Test health monitoring endpoint under load."""
        result = await load_tester.run_load_test(
            endpoint="/api/v1/orchestrate/health",
            concurrent_users=100,
            requests_per_user=10,
        )

        print("\nHealth Monitor Load Test Results:")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Success Rate: {result.successful_requests / result.total_requests * 100:.1f}%")
        print(f"  RPS: {result.requests_per_second:.1f}")

        assert result.successful_requests / result.total_requests > 0.99
        assert result.avg_response_time < 1.0

    async def test_mixed_endpoint_load(self, load_tester):
        """Test mixed workload across multiple endpoints."""
        endpoints = [
            ("/health", None, 40),
            ("/api/v1/orchestrate/health", None, 30),
            ("/api/v1/orchestrate/stats", None, 20),
            ("/api/v1/orchestrate/route", {"task": {"title": "test"}}, 10),
        ]

        all_results = []

        for endpoint, data, percentage in endpoints:
            users = int(100 * (percentage / 100))
            result = await load_tester.run_load_test(
                endpoint=endpoint,
                data=data,
                concurrent_users=max(users, 1),
                requests_per_user=10,
            )
            all_results.append((endpoint, result))

        # Print summary
        print("\nMixed Workload Load Test Results:")
        for endpoint, result in all_results:
            print(f"  {endpoint}:")
            print(f"    RPS: {result.requests_per_second:.1f}")
            print(f"    Success: {result.successful_requests / result.total_requests * 100:.1f}%")
            print(f"    Avg: {result.avg_response_time * 1000:.1f}ms")

        # Overall assertions
        total_success = sum(r.successful_requests for _, r in all_results)
        total_requests = sum(r.total_requests for _, r in all_results)
        assert total_success / total_requests > 0.95


@pytest.mark.performance
@pytest.mark.asyncio
class TestSustainedLoad:
    """Sustained load tests (longer duration)."""

    async def test_sustained_load_5_minutes(self, load_tester):
        """Test system under sustained load for 5 minutes."""
        # This would run for 5 minutes in real scenario
        # Shortened for test purposes

        results = []
        start_time = time.time()
        duration = 60  # 1 minute for test (would be 300 for 5 min)

        while time.time() - start_time < duration:
            result = await load_tester.run_load_test(
                endpoint="/health",
                concurrent_users=50,
                requests_per_user=5,
            )
            results.append(result)
            await asyncio.sleep(5)  # Brief pause between bursts

        # Analyze trends
        success_rates = [r.successful_requests / r.total_requests for r in results]
        response_times = [r.avg_response_time for r in results]

        print("\nSustained Load Test Results (1 minute):")
        print(f"  Min Success Rate: {min(success_rates) * 100:.1f}%")
        print(f"  Max Success Rate: {max(success_rates) * 100:.1f}%")
        print(f"  Avg Response Time: {sum(response_times) / len(response_times) * 1000:.1f}ms")
        print(f"  Max Response Time: {max(response_times) * 1000:.1f}ms")

        # Should maintain performance over time
        assert min(success_rates) > 0.95
        assert max(response_times) < 2.0

    async def test_ramp_up_ramp_down(self, load_tester):
        """Test system behavior during load ramp up and down."""
        stages = [
            (10, 10),  # 10 users, 10 requests each
            (50, 10),  # 50 users, 10 requests each
            (100, 10),  # 100 users, 10 requests each
            (150, 10),  # 150 users, 10 requests each
            (100, 10),  # Ramp down
            (50, 10),
            (10, 10),
        ]

        results = []
        for users, requests in stages:
            result = await load_tester.run_load_test(
                endpoint="/api/v1/orchestrate/health",
                concurrent_users=users,
                requests_per_user=requests,
            )
            results.append((users, result))
            print(
                f"  {users} users: {result.requests_per_second:.1f} RPS, "
                f"{result.avg_response_time * 1000:.1f}ms avg"
            )

        # Should handle ramp up without degradation
        max_users_result = max(results, key=lambda x: x[0])
        assert max_users_result[1].successful_requests / max_users_result[1].total_requests > 0.90


@pytest.mark.performance
@pytest.mark.asyncio
class TestStressLimits:
    """Stress tests to find system limits."""

    async def test_find_breaking_point(self, load_tester):
        """Gradually increase load until system breaks."""
        concurrent_users = 50
        max_users = 500
        step = 50

        breaking_point = None

        while concurrent_users <= max_users:
            print(f"\nTesting with {concurrent_users} concurrent users...")

            result = await load_tester.run_load_test(
                endpoint="/health",
                concurrent_users=concurrent_users,
                requests_per_user=5,
            )

            success_rate = result.successful_requests / result.total_requests
            print(f"  Success Rate: {success_rate * 100:.1f}%")
            print(f"  Avg Response: {result.avg_response_time * 1000:.1f}ms")

            # Consider it broken if success rate drops below 80%
            if success_rate < 0.80 or result.avg_response_time > 5.0:
                breaking_point = concurrent_users
                print(f"  BREAKING POINT FOUND: {breaking_point} users")
                break

            concurrent_users += step
            await asyncio.sleep(1)  # Cool down between tests

        if breaking_point:
            print(f"\nSystem breaking point: {breaking_point} concurrent users")
        else:
            print(f"\nSystem handled max tested load: {max_users} users")

    async def test_spike_recovery(self, load_tester):
        """Test recovery from traffic spike."""
        # Normal load
        print("Normal load...")
        normal_result = await load_tester.run_load_test(
            endpoint="/health",
            concurrent_users=20,
            requests_per_user=10,
        )
        print(f"  Normal: {normal_result.requests_per_second:.1f} RPS")

        # Spike
        print("Traffic spike...")
        spike_result = await load_tester.run_load_test(
            endpoint="/health",
            concurrent_users=200,
            requests_per_user=5,
        )
        print(
            f"  Spike: {spike_result.requests_per_second:.1f} RPS, "
            f"{spike_result.successful_requests / spike_result.total_requests * 100:.1f}% success"
        )

        # Recovery
        await asyncio.sleep(5)
        print("Recovery...")
        recovery_result = await load_tester.run_load_test(
            endpoint="/health",
            concurrent_users=20,
            requests_per_user=10,
        )
        print(f"  Recovery: {recovery_result.requests_per_second:.1f} RPS")

        # Should recover to normal performance
        assert recovery_result.requests_per_second >= normal_result.requests_per_second * 0.8


# Performance Benchmarks
"""
## Performance Benchmarks

### Target Performance

| Metric | Target | Critical |
|--------|--------|----------|
| Health Check | < 100ms | < 500ms |
| Route Request | < 500ms | < 2000ms |
| Workflow Create | < 2000ms | < 10000ms |
| Max RPS | 1000 | 500 |
| Error Rate | < 1% | < 5% |

### Load Test Schedule

- **Daily**: Quick smoke test (100 users, 1 min)
- **Weekly**: Full load test (500 users, 10 min)
- **Monthly**: Stress test (find breaking point)
- **Release**: Full suite before deployment

### Running Load Tests

```bash
# Quick smoke test
pytest tests/performance/test_load_orchestration.py -v -k "test_health_endpoint_load" --tb=short

# Full load test suite
pytest tests/performance/test_load_orchestration.py -v -m performance --tb=short

# Stress test (find limits)
pytest tests/performance/test_load_orchestration.py -v -k "test_find_breaking_point" --tb=short

# With profiling
cProfile -o load_test.prof -m pytest tests/performance/test_load_orchestration.py
```

### Interpreting Results

**Good Performance:**
- 99%+ success rate
- P95 response < 1s
- No errors in logs
- Stable RPS over time

**Degraded Performance:**
- 95-99% success rate
- P95 response 1-2s
- Some timeouts
- Gradual slowdown

**Critical:**
- < 95% success rate
- P95 response > 2s
- Frequent errors
- Rapid degradation

### Performance Tuning

If load tests fail:
1. Check resource usage (CPU, memory)
2. Increase DB connection pool
3. Scale horizontally (more nodes)
4. Enable caching
5. Optimize slow queries
"""


async def async_main():
    """Main entry point for direct execution."""
    tester = LoadTester()

    print("Running load tests...")

    # Quick health check load test
    result = await tester.run_load_test(
        endpoint="/health",
        concurrent_users=100,
        requests_per_user=10,
    )

    print("\nResults:")
    print(f"  Total: {result.total_requests}")
    print(f"  Success: {result.successful_requests}")
    print(f"  Failed: {result.failed_requests}")
    print(f"  RPS: {result.requests_per_second:.1f}")
    print(f"  Avg: {result.avg_response_time * 1000:.1f}ms")
    print(f"  P95: {result.percentile_95 * 1000:.1f}ms")
    print(f"  P99: {result.percentile_99 * 1000:.1f}ms")

    await tester.close()


if __name__ == "__main__":
    # Stond tot 2026-08-01 BOVEN de definitie van async_main, waardoor direct uitvoeren
    # van dit bestand een NameError gaf. In pytest viel dat nooit op omdat het blok daar
    # niet draait.
    asyncio.run(async_main())
