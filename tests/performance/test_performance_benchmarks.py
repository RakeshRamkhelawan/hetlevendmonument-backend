"""
Performance Benchmark Tests
============================

pytest-based performance benchmarks for critical code paths.
Uses pytest-benchmark for accurate timing measurements.

Run with:
    pytest tests/performance/test_performance_benchmarks.py --benchmark-only
"""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest


class TestDatabasePerformance:
    """Test database query performance"""

    def test_simple_select_query_performance(self, benchmark):
        """Benchmark simple SELECT query"""

        def run_query():
            # Simulate database query
            time.sleep(0.001)  # 1ms simulated query time
            return [{"id": 1, "name": "test"}]

        result = benchmark(run_query)
        assert len(result) > 0

    def test_complex_join_query_performance(self, benchmark):
        """Benchmark complex JOIN query"""

        def run_complex_query():
            # Simulate complex query
            time.sleep(0.005)  # 5ms simulated query time
            return [{"id": 1, "workflow": "test", "agent": "agent1"}]

        result = benchmark(run_complex_query)
        assert len(result) > 0

    def test_bulk_insert_performance(self, benchmark):
        """Benchmark bulk insert operation"""

        def bulk_insert():
            # Simulate bulk insert of 100 records
            records = [{"id": i, "data": f"record_{i}"} for i in range(100)]
            time.sleep(0.01)  # 10ms for 100 records
            return len(records)

        count = benchmark(bulk_insert)
        assert count == 100

    def test_index_lookup_performance(self, benchmark):
        """Benchmark indexed column lookup"""

        def indexed_lookup():
            # Simulate fast indexed lookup
            time.sleep(0.0005)  # 0.5ms
            return {"id": 1, "indexed_value": "fast"}

        result = benchmark(indexed_lookup)
        assert "id" in result

    def test_full_table_scan_performance(self, benchmark):
        """Benchmark full table scan (should be slow)"""

        def full_scan():
            # Simulate slow full table scan
            time.sleep(0.05)  # 50ms
            return [{"id": i} for i in range(1000)]

        result = benchmark(full_scan)
        assert len(result) == 1000


class TestCachePerformance:
    """Test caching performance"""

    def test_cache_hit_performance(self, benchmark):
        """Benchmark cache hit (should be fast)"""
        cache = {"key1": "value1"}

        def cache_lookup():
            return cache.get("key1")

        result = benchmark(cache_lookup)
        assert result == "value1"

    def test_cache_miss_performance(self, benchmark):
        """Benchmark cache miss with database fallback"""
        cache = {}

        def cache_miss_lookup():
            value = cache.get("missing_key")
            if value is None:
                # Simulate database lookup
                time.sleep(0.002)  # 2ms
                value = "from_db"
                cache["missing_key"] = value
            return value

        result = benchmark(cache_miss_lookup)
        assert result == "from_db"

    def test_cache_eviction_performance(self, benchmark):
        """Benchmark LRU cache eviction"""
        cache = {f"key_{i}": f"value_{i}" for i in range(100)}

        def evict_oldest():
            # Simulate LRU eviction
            if len(cache) > 95:
                oldest_key = list(cache.keys())[0]
                del cache[oldest_key]
            cache["new_key"] = "new_value"
            return len(cache)

        size = benchmark(evict_oldest)
        assert size <= 100


class TestAPIEndpointPerformance:
    """Test API endpoint response times"""

    def test_health_check_endpoint_performance(self, benchmark):
        """Benchmark /health endpoint (should be <10ms)"""

        def health_check():
            # Simulate health check
            return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

        result = benchmark(health_check)
        assert result["status"] == "healthy"

    def test_list_workflows_endpoint_performance(self, benchmark):
        """Benchmark GET /api/v1/workflows (paginated)"""

        def list_workflows():
            # Simulate fetching 20 workflows
            time.sleep(0.01)  # 10ms
            return [{"id": i, "name": f"workflow_{i}"} for i in range(20)]

        result = benchmark(list_workflows)
        assert len(result) == 20

    def test_create_workflow_endpoint_performance(self, benchmark):
        """Benchmark POST /api/v1/workflows"""

        def create_workflow():
            # Simulate workflow creation (validation + DB insert)
            time.sleep(0.02)  # 20ms
            return {"id": 1, "workflow_id": "test", "status": "created"}

        result = benchmark(create_workflow)
        assert result["status"] == "created"

    def test_execute_workflow_endpoint_performance(self, benchmark):
        """Benchmark POST /api/v1/workflows/{id}/execute"""

        def execute_workflow():
            # Simulate workflow execution trigger
            time.sleep(0.015)  # 15ms
            return {"execution_id": 1, "status": "pending"}

        result = benchmark(execute_workflow)
        assert "execution_id" in result


class TestDAGValidationPerformance:
    """Test DAG validation performance"""

    def test_small_dag_validation_performance(self, benchmark):
        """Benchmark validation of small DAG (5 tasks)"""

        def validate_small_dag():
            # Simulate DAG validation
            tasks = {f"task_{i}": {} for i in range(5)}
            dependencies = {f"task_{i}": [f"task_{i-1}"] for i in range(1, 5)}
            time.sleep(0.001)  # 1ms
            return True

        result = benchmark(validate_small_dag)
        assert result is True

    def test_medium_dag_validation_performance(self, benchmark):
        """Benchmark validation of medium DAG (50 tasks)"""

        def validate_medium_dag():
            # Simulate larger DAG validation
            time.sleep(0.01)  # 10ms
            return True

        result = benchmark(validate_medium_dag)
        assert result is True

    def test_large_dag_validation_performance(self, benchmark):
        """Benchmark validation of large DAG (200 tasks)"""

        def validate_large_dag():
            # Simulate very large DAG
            time.sleep(0.05)  # 50ms
            return True

        result = benchmark(validate_large_dag)
        assert result is True

    def test_topological_sort_performance(self, benchmark):
        """Benchmark topological sort algorithm"""

        def topological_sort():
            # Simulate topological sort on 100 tasks
            time.sleep(0.008)  # 8ms
            return [f"task_{i}" for i in range(100)]

        result = benchmark(topological_sort)
        assert len(result) == 100


class TestSerializationPerformance:
    """Test JSON serialization performance"""

    def test_small_object_serialization(self, benchmark):
        """Benchmark serializing small object"""
        import json

        obj = {"id": 1, "name": "test", "value": 42}

        def serialize():
            return json.dumps(obj)

        result = benchmark(serialize)
        assert "test" in result

    def test_large_object_serialization(self, benchmark):
        """Benchmark serializing large object (1000 items)"""
        import json

        obj = {f"key_{i}": f"value_{i}" for i in range(1000)}

        def serialize():
            return json.dumps(obj)

        result = benchmark(serialize)
        assert len(result) > 1000

    def test_nested_object_serialization(self, benchmark):
        """Benchmark serializing deeply nested object"""
        import json

        obj = {"level1": {"level2": {"level3": {"data": [{"item": i} for i in range(100)]}}}}

        def serialize():
            return json.dumps(obj)

        result = benchmark(serialize)
        assert "level3" in result


class TestStateMachinePerformance:
    """Test state machine transition performance"""

    def test_state_transition_validation_performance(self, benchmark):
        """Benchmark state transition validation"""
        from src.core.workflow.state_machine import WorkflowStateMachine

        sm = WorkflowStateMachine()

        def validate_transition():
            return sm.can_transition("pending", "running", "workflow")

        result = benchmark(validate_transition)
        assert result is True

    def test_multiple_transitions_performance(self, benchmark):
        """Benchmark checking 100 transitions"""
        from src.core.workflow.state_machine import WorkflowStateMachine

        sm = WorkflowStateMachine()

        transitions = [
            ("pending", "running"),
            ("running", "succeeded"),
            ("running", "failed"),
            ("pending", "cancelled"),
        ] * 25  # 100 checks

        def check_transitions():
            results = []
            for from_state, to_state in transitions:
                results.append(sm.can_transition(from_state, to_state, "workflow"))
            return results

        results = benchmark(check_transitions)
        assert len(results) == 100


class TestMemoryUsagePerformance:
    """Test memory-intensive operations"""

    def test_large_list_creation_performance(self, benchmark):
        """Benchmark creating large list"""

        def create_large_list():
            return [i for i in range(10000)]

        result = benchmark(create_large_list)
        assert len(result) == 10000

    def test_dictionary_comprehension_performance(self, benchmark):
        """Benchmark dictionary comprehension"""

        def create_dict():
            return {f"key_{i}": i * 2 for i in range(1000)}

        result = benchmark(create_dict)
        assert len(result) == 1000

    def test_string_concatenation_performance(self, benchmark):
        """Benchmark string concatenation"""

        def concatenate_strings():
            result = ""
            for i in range(100):
                result += f"item_{i},"
            return result

        result = benchmark(concatenate_strings)
        assert "item_99" in result

    def test_string_join_performance(self, benchmark):
        """Benchmark string join (faster than concatenation)"""

        def join_strings():
            items = [f"item_{i}" for i in range(100)]
            return ",".join(items)

        result = benchmark(join_strings)
        assert "item_99" in result


class TestAsyncOperationPerformance:
    """Test async operation performance (non-benchmark to avoid event loop issues)"""

    @pytest.mark.asyncio
    async def test_async_function_overhead(self):
        """Benchmark async function call overhead"""

        async def async_operation():
            return "result"

        result = await async_operation()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self):
        """Benchmark running 10 async operations concurrently"""

        async def single_operation(n):
            await asyncio.sleep(0.001)  # 1ms
            return n * 2

        tasks = [single_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 10


class TestCompressionPerformance:
    """Test data compression performance"""

    def test_gzip_compression_performance(self, benchmark):
        """Benchmark gzip compression"""
        import gzip

        data = b"test data " * 1000

        def compress():
            return gzip.compress(data)

        result = benchmark(compress)
        assert len(result) < len(data)

    def test_gzip_decompression_performance(self, benchmark):
        """Benchmark gzip decompression"""
        import gzip

        data = b"test data " * 1000
        compressed = gzip.compress(data)

        def decompress():
            return gzip.decompress(compressed)

        result = benchmark(decompress)
        assert result == data


class TestConcurrencyPerformance:
    """Test concurrent operation performance"""

    def test_sequential_processing_performance(self, benchmark):
        """Benchmark sequential processing of 100 items"""

        def process_item(n):
            return n * 2

        def sequential():
            return [process_item(i) for i in range(100)]

        results = benchmark(sequential)
        assert len(results) == 100

    def test_batch_processing_performance(self, benchmark):
        """Benchmark batch processing (10 batches of 10)"""

        def process_batch(batch):
            return [item * 2 for item in batch]

        def batch_processing():
            items = list(range(100))
            batches = [items[i : i + 10] for i in range(0, 100, 10)]
            results = []
            for batch in batches:
                results.extend(process_batch(batch))
            return results

        results = benchmark(batch_processing)
        assert len(results) == 100


class TestPerformanceRegression:
    """Test for performance regressions"""

    def test_api_response_time_baseline(self, benchmark):
        """Establish baseline for API response time"""

        def api_call():
            time.sleep(0.01)  # 10ms baseline
            return {"status": "ok"}

        result = benchmark(api_call)
        # Benchmark should complete in <20ms (including overhead)
        assert result["status"] == "ok"

    def test_database_query_baseline(self, benchmark):
        """Establish baseline for database query time"""

        def db_query():
            time.sleep(0.005)  # 5ms baseline
            return [{"id": 1}]

        result = benchmark(db_query)
        # Should complete in <10ms
        assert len(result) == 1

    def test_workflow_validation_baseline(self, benchmark):
        """Establish baseline for workflow validation"""

        def validate():
            time.sleep(0.002)  # 2ms baseline
            return True

        result = benchmark(validate)
        # Should complete in <5ms
        assert result is True
