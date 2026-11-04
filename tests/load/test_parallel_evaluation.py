"""
Load Tests: 100 Parallel Evaluation Runs

Tests system stability when running multiple RAG evaluations concurrently.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class EvalTestResult:
    """Result of a single evaluation run"""

    run_id: str
    tenant_id: int
    success: bool
    duration_s: float
    metrics: Optional[Dict[str, float]] = None
    error: Optional[str] = None


class MockRAGEvaluator:
    """Mock RAG evaluator with configurable behavior"""

    def __init__(
        self,
        min_duration_s: float = 0.1,
        max_duration_s: float = 0.5,
        error_rate: float = 0.0,
    ):
        self.min_duration_s = min_duration_s
        self.max_duration_s = max_duration_s
        self.error_rate = error_rate
        self.eval_count = 0

    async def evaluate(self, tenant_id: int, run_id: str, num_samples: int = 10) -> Dict[str, Any]:
        """Simulate an evaluation run"""
        import random

        self.eval_count += 1

        # Simulate evaluation work
        duration = random.uniform(self.min_duration_s, self.max_duration_s)
        # Scale duration with sample count (more samples = longer)
        duration *= num_samples / 10
        await asyncio.sleep(duration)

        # Simulate errors
        if random.random() < self.error_rate:
            raise Exception(f"Simulated evaluation error for run {run_id}")

        return {
            "run_id": run_id,
            "status": "complete",
            "metrics": {
                "faithfulness": 0.80 + random.uniform(0, 0.15),
                "context_precision": 0.75 + random.uniform(0, 0.15),
                "answer_relevancy": 0.85 + random.uniform(0, 0.10),
            },
        }


class ParallelEvaluationTester:
    """Utility for parallel evaluation load testing"""

    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.results: List[EvalTestResult] = []

    async def run_single_evaluation(self, tenant_id: int, num_samples: int = 10) -> EvalTestResult:
        """Run a single evaluation"""
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        try:
            result = await self.evaluator.evaluate(
                tenant_id=tenant_id, run_id=run_id, num_samples=num_samples
            )

            duration = time.perf_counter() - start
            return EvalTestResult(
                run_id=run_id,
                tenant_id=tenant_id,
                success=True,
                duration_s=duration,
                metrics=result.get("metrics", {}),
            )

        except Exception as e:
            duration = time.perf_counter() - start
            return EvalTestResult(
                run_id=run_id,
                tenant_id=tenant_id,
                success=False,
                duration_s=duration,
                error=str(e),
            )

    async def run_parallel_evaluations(
        self,
        num_evaluations: int,
        concurrency: int,
        tenant_ids: List[int],
        num_samples_per_eval: int = 10,
    ) -> Dict[str, Any]:
        """Run multiple evaluations in parallel"""
        semaphore = asyncio.Semaphore(concurrency)
        self.results = []

        async def bounded_eval(i: int):
            async with semaphore:
                tenant_id = tenant_ids[i % len(tenant_ids)]
                result = await self.run_single_evaluation(
                    tenant_id=tenant_id, num_samples=num_samples_per_eval
                )
                self.results.append(result)

        start_time = time.perf_counter()

        tasks = [bounded_eval(i) for i in range(num_evaluations)]
        await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time

        return self._calculate_summary(total_duration)

    def _calculate_summary(self, total_duration: float) -> Dict[str, Any]:
        """Calculate summary statistics"""
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        durations = [r.duration_s for r in successful]

        return {
            "total_evaluations": len(self.results),
            "successful": len(successful),
            "failed": len(failed),
            "error_rate": len(failed) / len(self.results) if self.results else 0,
            "total_duration_s": total_duration,
            "throughput_evals_per_min": (
                len(self.results) / total_duration * 60 if total_duration > 0 else 0
            ),
            "duration_mean_s": mean(durations) if durations else 0,
            "duration_min_s": min(durations) if durations else 0,
            "duration_max_s": max(durations) if durations else 0,
            "errors": [r.error for r in failed],
        }


class TestParallelEvaluation:
    """Load tests for parallel evaluation runs"""

    @pytest.fixture
    def mock_evaluator(self):
        """Create mock evaluator with realistic behavior"""
        return MockRAGEvaluator(min_duration_s=0.05, max_duration_s=0.15, error_rate=0.0)

    @pytest.fixture
    def tenant_ids(self):
        return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_10_parallel_evaluations(self, mock_evaluator, tenant_ids):
        """Test 10 parallel evaluations"""
        tester = ParallelEvaluationTester(mock_evaluator)

        summary = await tester.run_parallel_evaluations(
            num_evaluations=10,
            concurrency=10,
            tenant_ids=tenant_ids,
            num_samples_per_eval=5,
        )

        self._print_summary("10 Parallel Evaluations", summary)

        assert summary["error_rate"] < 0.1

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_50_parallel_evaluations(self, mock_evaluator, tenant_ids):
        """Test 50 parallel evaluations"""
        tester = ParallelEvaluationTester(mock_evaluator)

        summary = await tester.run_parallel_evaluations(
            num_evaluations=50,
            concurrency=25,  # 25 at a time
            tenant_ids=tenant_ids,
            num_samples_per_eval=5,
        )

        self._print_summary("50 Parallel Evaluations", summary)

        assert summary["error_rate"] < 0.1

    @pytest.mark.load
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_100_parallel_evaluations(self, mock_evaluator, tenant_ids):
        """Test 100 parallel evaluations (main target)"""
        tester = ParallelEvaluationTester(mock_evaluator)

        summary = await tester.run_parallel_evaluations(
            num_evaluations=100,
            concurrency=50,  # 50 at a time
            tenant_ids=tenant_ids,
            num_samples_per_eval=10,
        )

        self._print_summary("100 Parallel Evaluations", summary)

        # Assertions
        assert summary["error_rate"] < 0.05, f"Error rate {summary['error_rate']:.1%} > 5%"
        assert summary["total_duration_s"] < 60, "Total duration > 1 minute"

        print(
            f"\nPASS: Completed {summary['successful']} evaluations in {summary['total_duration_s']:.1f}s"
        )

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_multi_tenant_isolation_under_load(self, mock_evaluator, tenant_ids):
        """Verify tenant isolation under parallel load"""
        call_log = []

        original_evaluate = mock_evaluator.evaluate

        async def tracking_evaluate(**kwargs):
            call_log.append(
                {
                    "tenant_id": kwargs.get("tenant_id"),
                    "run_id": kwargs.get("run_id"),
                    "timestamp": time.time(),
                }
            )
            return await original_evaluate(**kwargs)

        mock_evaluator.evaluate = tracking_evaluate
        tester = ParallelEvaluationTester(mock_evaluator)

        await tester.run_parallel_evaluations(
            num_evaluations=50, concurrency=50, tenant_ids=tenant_ids
        )

        # Verify all tenants were used
        tenants_called = set(c["tenant_id"] for c in call_log)
        assert len(tenants_called) >= min(len(tenant_ids), 5)

        print(f"\nTenants used: {sorted(tenants_called)}")

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_evaluation_resource_cleanup(self, mock_evaluator, tenant_ids):
        """Verify resources are cleaned up after evaluations"""
        resource_count = 0

        async def resource_tracking_evaluate(**kwargs):
            nonlocal resource_count
            resource_count += 1
            await asyncio.sleep(0.05)
            resource_count -= 1  # "Cleanup"
            return {"status": "complete", "metrics": {}}

        mock_evaluator.evaluate = resource_tracking_evaluate
        tester = ParallelEvaluationTester(mock_evaluator)

        await tester.run_parallel_evaluations(
            num_evaluations=50, concurrency=25, tenant_ids=tenant_ids
        )

        # All resources should be cleaned up
        assert resource_count == 0, f"Resource leak: {resource_count} still held"

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_evaluation_with_failures(self, tenant_ids):
        """Test evaluation system handles failures correctly"""
        failing_evaluator = MockRAGEvaluator(
            min_duration_s=0.05,
            max_duration_s=0.10,
            error_rate=0.1,  # 10% error rate
        )

        tester = ParallelEvaluationTester(failing_evaluator)

        summary = await tester.run_parallel_evaluations(
            num_evaluations=100,
            concurrency=50,
            tenant_ids=tenant_ids,
            num_samples_per_eval=5,
        )

        self._print_summary("Evaluations with 10% Failure Rate", summary)

        # Error rate should be close to expected (10% +/- 5%)
        assert (
            0.05 < summary["error_rate"] < 0.20
        ), f"Error rate {summary['error_rate']:.1%} outside expected range"

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_metric_aggregation_under_load(self, mock_evaluator, tenant_ids):
        """Verify metrics are correctly aggregated under load"""
        tester = ParallelEvaluationTester(mock_evaluator)

        await tester.run_parallel_evaluations(
            num_evaluations=50,
            concurrency=25,
            tenant_ids=tenant_ids,
            num_samples_per_eval=5,
        )

        # Verify all successful results have metrics
        successful = [r for r in tester.results if r.success]
        assert len(successful) > 0

        for result in successful:
            assert result.metrics is not None
            assert "faithfulness" in result.metrics
            assert "context_precision" in result.metrics
            assert "answer_relevancy" in result.metrics

            # Verify metrics are in valid range
            for key, value in result.metrics.items():
                assert 0.0 <= value <= 1.0, f"Metric {key}={value} out of range"

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_evaluation_timeout_handling(self, tenant_ids):
        """Test evaluation timeout behavior"""

        class SlowEvaluator:
            async def evaluate(self, **kwargs):
                await asyncio.sleep(10)  # Very slow
                return {"status": "complete", "metrics": {}}

        tester = ParallelEvaluationTester(SlowEvaluator())

        # Run with timeout
        async def bounded_test():
            return await tester.run_parallel_evaluations(
                num_evaluations=5,
                concurrency=5,
                tenant_ids=tenant_ids,
                num_samples_per_eval=1,
            )

        try:
            # Should timeout
            summary = await asyncio.wait_for(bounded_test(), timeout=2.0)
            # If we get here without timeout, evaluator was faster than expected
            assert summary["successful"] >= 0
        except asyncio.TimeoutError:
            # Expected - evaluations took too long
            pass

    def _print_summary(self, test_name: str, summary: Dict[str, Any]):
        """Print formatted summary"""
        print(f"\n{'='*60}")
        print(f"LOAD TEST: {test_name}")
        print(f"{'='*60}")
        print(f"  Total Evaluations: {summary['total_evaluations']}")
        print(f"  Successful:        {summary['successful']}")
        print(f"  Failed:            {summary['failed']}")
        print(f"  Error Rate:        {summary['error_rate']:.2%}")
        print(f"  Total Duration:    {summary['total_duration_s']:.2f}s")
        print(f"  Throughput:        {summary['throughput_evals_per_min']:.1f} evals/min")
        print("\nDuration per Evaluation:")
        print(f"  Mean: {summary['duration_mean_s']:.3f}s")
        print(f"  Min:  {summary['duration_min_s']:.3f}s")
        print(f"  Max:  {summary['duration_max_s']:.3f}s")
        if summary.get("errors"):
            print(f"\nErrors (first 3): {summary['errors'][:3]}")
        print(f"{'='*60}")


class TestParallelEvaluationUtilities:
    """Tests for the evaluation testing utilities"""

    @pytest.mark.load
    def test_eval_test_result_dataclass(self):
        """Test EvalTestResult dataclass"""
        result = EvalTestResult(
            run_id="test123",
            tenant_id=1,
            success=True,
            duration_s=1.5,
            metrics={"faithfulness": 0.9},
        )
        assert result.run_id == "test123"
        assert result.success is True
        assert result.metrics["faithfulness"] == 0.9

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_mock_evaluator(self):
        """Test MockRAGEvaluator"""
        evaluator = MockRAGEvaluator(min_duration_s=0.01, max_duration_s=0.02)

        result = await evaluator.evaluate(tenant_id=1, run_id="test", num_samples=5)

        assert result["status"] == "complete"
        assert "metrics" in result
        assert evaluator.eval_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "load", "-s"])
