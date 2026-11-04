"""
Performance Benchmarks for ALS 2.0

Run benchmarks:
    python -m pytest tests/performance/benchmark.py -v

Or with pytest-benchmark:
    pytest tests/performance/benchmark.py --benchmark-only
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List

import pytest

from src.core.als.enterprise.audit.audit_logger import AuditEventType, AuditLogger
from src.core.als.enterprise.contracts.schema_registry import (
    DataSchema,
    SchemaRef,
    SchemaRegistry,
    SemVer,
)
from src.core.als.enterprise.events.event_store import EventStore, EventType


def _compute_schema_hash(json_schema: dict) -> str:
    """Compute schema hash for tests."""
    import hashlib
    import json

    canonical = json.dumps(json_schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


class TestSchemaRegistryBenchmark:
    """Benchmark SchemaRegistry operations."""

    def test_schema_registration_benchmark(self):
        """Benchmark schema registration."""
        registry = SchemaRegistry()
        timestamp = datetime.now(timezone.utc).isoformat()

        start = time.time()
        for i in range(100):
            schema_hash = _compute_schema_hash({"type": "object"})
            schema = DataSchema(
                schema_ref=SchemaRef(
                    domain="test",
                    name=f"schema_{i}",
                    version=SemVer(major=1, minor=0, patch=0),
                ),
                json_schema={"type": "object"},
                schema_hash=schema_hash,
                created_at=timestamp,
                created_by="benchmark",
            )
            registry.register(schema)
        elapsed = time.time() - start

        # Should register 100 schemas in < 1 second
        assert elapsed < 1.0
        assert len(registry._schemas) == 100

    def test_schema_lookup_benchmark(self):
        """Benchmark schema lookup."""
        registry = SchemaRegistry()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Pre-populate
        for i in range(1000):
            schema_hash = _compute_schema_hash({"type": "object"})
            schema = DataSchema(
                schema_ref=SchemaRef(
                    domain="test",
                    name=f"schema_{i}",
                    version=SemVer(major=1, minor=0, patch=0),
                ),
                json_schema={"type": "object"},
                schema_hash=schema_hash,
                created_at=timestamp,
                created_by="benchmark",
            )
            registry.register(schema)

        start = time.time()
        results = []
        for i in range(100):
            result = registry.get(f"test.schema_{i}@1.0.0")
            results.append(result)
        elapsed = time.time() - start

        # Should lookup 100 schemas in < 100ms
        assert elapsed < 0.1
        assert len(results) == 100
        assert all(r is not None for r in results)


class TestEventStoreBenchmark:
    """Benchmark EventStore operations."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_event_append_benchmark(self, benchmark):
        """Benchmark event appending."""
        store = EventStore()

        async def append_events():
            for i in range(1000):
                from src.core.als.enterprise.events.event_store import Event

                event = Event(
                    event_id=f"evt-{i}",
                    event_type=EventType.CONTRACT_PROPOSED,
                    tenant_id=1,
                    aggregate_id=f"contract-{i % 100}",
                    aggregate_type="contract",
                    payload={"seq": i},
                    timestamp=datetime.now(timezone.utc),
                    previous_hash="0" * 32,
                )
                await store.append(event)

        start = time.time()
        await append_events()
        elapsed = time.time() - start

        # Should handle 1000 events in < 1 second
        assert elapsed < 1.0
        assert len(store._events) == 1000

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_event_query_benchmark(self, benchmark):
        """Benchmark event querying."""
        store = EventStore()

        # Pre-populate with 10,000 events
        for i in range(10000):
            from src.core.als.enterprise.events.event_store import Event

            event = Event(
                event_id=f"evt-{i}",
                event_type=EventType.CONTRACT_PROPOSED if i % 2 == 0 else EventType.CONTRACT_AGREED,
                tenant_id=i % 10,
                aggregate_id=f"contract-{i % 100}",
                aggregate_type="contract",
                payload={"seq": i},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            await store.append(event)

        def query_events():
            # Query by aggregate
            events = store.get_events_by_aggregate("contract-50")
            # Query by tenant
            events = store.get_events_by_tenant(5)
            # Query by type
            events = store.query_events(event_type=EventType.CONTRACT_PROPOSED)

        start = time.time()
        query_events()
        elapsed = time.time() - start

        # Should query 10,000 events in < 100ms
        assert elapsed < 0.1


class TestAuditLoggerBenchmark:
    """Benchmark AuditLogger operations."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_audit_log_benchmark(self, benchmark):
        """Benchmark audit logging."""
        logger = AuditLogger(tenant_id=1)

        async def log_events():
            for i in range(1000):
                await logger.log_contract_event(
                    event_type=AuditEventType.CONTRACT_PROPOSED,
                    contract_id=f"contract-{i}",
                    actor_id=f"agent-{i % 100}",
                    details={"prana_cost": 50},
                )

        start = time.time()
        await log_events()
        elapsed = time.time() - start

        # Should log 1000 events in < 1 second
        assert elapsed < 1.0
        assert len(logger._events) == 1000


# NOTE: TestChiefOrchestratorBenchmark + test_100_concurrent_agents removed --
# both depended on src.core.als.enterprise.chief_orchestrator.ChiefOrchestrator,
# deleted as part of the confirmed-orphaned enterprise ChiefOrchestrator island
# cleanup (0 production callers -- see ADR-036 D12 / audit-to-fix AUDIT-005).


class TestConcurrentLoadBenchmark:
    """Test concurrent load scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_1000_events_per_second(self):
        """Test event store handles 1000 events/second."""
        store = EventStore()

        target_events = 1000
        start = time.time()

        # Generate events
        from src.core.als.enterprise.events.event_store import Event

        tasks = []
        for i in range(target_events):
            event = Event(
                event_id=f"evt-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id=f"contract-{i % 10}",
                aggregate_type="contract",
                payload={"seq": i},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            tasks.append(store.append(event))

        await asyncio.gather(*tasks)

        elapsed = time.time() - start
        rate = target_events / elapsed

        print(f"Events/sec: {rate:.1f}")

        # Should achieve > 500 events/second
        assert rate > 500


# Performance thresholds
PERFORMANCE_THRESHOLDS = {
    "schema_registration": {"max_ms": 10, "target_ops_per_sec": 100},
    "event_append": {"max_ms": 1, "target_ops_per_sec": 1000},
    "event_query": {"max_ms": 50, "target_ops_per_sec": 100},
    "audit_log": {"max_ms": 1, "target_ops_per_sec": 1000},
    "tenant_registration": {"max_ms": 50, "target_ops_per_sec": 20},
}


if __name__ == "__main__":
    # Run benchmarks directly
    pytest.main([__file__, "-v", "--benchmark-only"])
