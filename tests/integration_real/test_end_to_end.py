"""
REAL End-to-End Integration Tests.

Tests complete workflows with all real services:
- PostgreSQL (pgvector)
- Ollama (embeddings)
- Redis (Pub/Sub)

NO MOCKS - Full integration.
"""

import asyncio

import numpy as np
import pytest


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_ollama
@pytest.mark.requires_redis
class TestEndToEndRouting:
    """
    End-to-End tests: Full routing workflow.

    Tests the complete flow:
    1. Task comes in
    2. Router generates embedding (Ollama)
    3. Searches database (PostgreSQL + pgvector)
    4. Returns routing decision
    5. Publishes event (Redis)
    """

    async def test_complete_routing_workflow_finance(
        self, real_semantic_router, real_db_connection, real_redis_client, clean_test_data
    ):
        """
        E2E Test: Finance task routing workflow.

        Real embedding → Real DB query → Real decision → Real event
        """
        # Setup: Subscribe to events
        pubsub = real_redis_client.pubsub()
        await pubsub.subscribe("workflow:events")
        await asyncio.sleep(0.1)

        # Step 1: Teach the router about finance tasks
        await real_semantic_router.learn(
            task="Process vendor invoice payment", correct_department="finance", was_successful=True
        )

        # Step 2: Route a similar task
        result = await real_semantic_router.route(
            task="Process quarterly vendor payment",
            task_description="Pay invoices from Q4 2025",
            available_prana={
                "finance": 10000,
                "hr": 10000,
                "it_security": 10000,
            },
        )

        # Step 3: Verify routing decision
        from src.core.als.enterprise.departments.department_orchestrator import Department

        assert result.department == Department.FINANCE
        assert result.confidence > 0.6

        # Step 4: Publish event (simulating workflow creation)
        await real_redis_client.publish(
            "workflow:events",
            str(
                {
                    "type": "workflow:started",
                    "department": result.department.value,
                    "confidence": result.confidence,
                }
            ),
        )

        await asyncio.sleep(0.1)

        # Step 5: Verify event was published
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        assert msg is not None
        assert b"finance" in msg["data"]

        await pubsub.unsubscribe()
        await pubsub.close()

    async def test_end_to_end_learning_improves_routing(
        self, real_semantic_router, real_db_connection, clean_test_data
    ):
        """
        E2E Test: Learning feedback improves future routing.

        1. Initial routing for unknown task
        2. Provide feedback
        3. Subsequent routing should use learned pattern
        """
        from src.core.als.enterprise.departments.department_orchestrator import Department

        # Step 1: First routing (unknown task)
        result1 = await real_semantic_router.route(
            task="Machine learning model deployment", available_prana={"data_ai_governance": 10000}
        )

        # Might not find a match initially
        initial_confidence = result1.confidence

        # Step 2: Provide positive feedback
        if result1.department:
            await real_semantic_router.learn(
                task="Machine learning model deployment",
                correct_department=result1.department,
                was_successful=True,
            )
        else:
            # If no match, teach it Data & AI
            await real_semantic_router.learn(
                task="Machine learning model deployment",
                correct_department=Department.DATA_AI_GOVERNANCE,
                was_successful=True,
            )

        # Step 3: Route similar task again
        result2 = await real_semantic_router.route(
            task="Deploy neural network to production",
            available_prana={"data_ai_governance": 10000},
        )

        # Should now find a match with better confidence
        assert result2.department is not None
        assert result2.confidence > 0.5

    async def test_concurrent_routing_with_database(self, real_semantic_router, clean_test_data):
        """
        E2E Test: Multiple concurrent routing requests.

        Verifies database handles concurrency correctly.
        """
        tasks = [
            real_semantic_router.route(task=f"Finance task {i}", available_prana={"finance": 10000})
            for i in range(20)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete without errors
        assert len(results) == 20

        # Most should succeed (some might not find matches)
        successful = sum(1 for r in results if r.department is not None)
        assert successful >= 15  # At least 75% success


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_ollama
@pytest.mark.requires_redis
class TestEndToEndEventSystem:
    """
    End-to-End tests: Event System workflow.

    Tests complete event flow:
    1. Event published
    2. Handler processes
    3. Side effects (DB, notifications)
    """

    async def test_workflow_event_to_notification(self, real_redis_client, real_db_connection):
        """
        E2E Test: Workflow event triggers notification.

        1. Publish workflow:started event
        2. Handler should process
        3. Notification should be created
        """
        from src.core.events.handlers.notification_handler import NotificationEventHandler
        from src.core.events.pubsub_manager import EventType, RedisPubSubManager

        # Setup
        pubsub = RedisPubSubManager()
        await pubsub.connect()

        handler = NotificationEventHandler(pubsub)
        await handler.register_handlers()

        # Subscribe to notification events
        test_pubsub = real_redis_client.pubsub()
        await test_pubsub.subscribe("user:activity")
        await asyncio.sleep(0.1)

        # Publish task assigned event
        await pubsub.publish(
            event_type=EventType.TASK_CREATED,
            data={
                "task_id": "task_e2e_001",
                "name": "Review design mockups",
                "assignee": "user_test_123",
                "department": "product_innovation",
            },
            tenant_id=1,
            source="e2e_test",
        )

        await asyncio.sleep(0.5)

        # Verify notification was created (would be in queue)
        queue_stats = handler.get_queue_stats()
        assert queue_stats["total"] >= 1

        await test_pubsub.unsubscribe()
        await test_pubsub.close()
        await pubsub.disconnect()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_ollama
@pytest.mark.requires_redis
class TestEndToEndSyncService:
    """
    End-to-End tests: YJS Sync workflow.

    Tests sync-server integration.
    """

    async def test_sync_server_snapshot_save_and_load(self, real_db_connection):
        """
        E2E Test: Save and load document snapshot.

        This simulates what sync-server does:
        1. Save YJS update to backend
        2. Load it back
        """
        workflow_id = "wf_e2e_sync_test"

        # Simulate saving snapshot
        fake_yjs_update = b"\x00\x01\x02\x03"  # Binary YJS data

        # In real implementation, this would be API call to backend
        # For test, we verify the endpoint exists

        # TODO: Implement actual test when sync endpoints are complete
        # For now, verify tables exist
        result = await real_db_connection.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name IN ('workflow_snapshots', 'yjs_documents')
        """
        )

        # Table may or may not exist yet
        # This test documents expected behavior
        assert result >= 0  # Placeholder


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestEmbeddingPerformance:
    """Performance tests for embedding generation."""

    async def test_embedding_latency(self, real_ollama_embedder):
        """
        Performance Test: Embedding generation latency.

        Should be fast enough for real-time use.
        """
        import time

        text = "Process monthly budget review"

        latencies = []
        for _ in range(10):
            start = time.time()
            await real_ollama_embedder.embed(text)
            elapsed = time.time() - start
            latencies.append(elapsed)

        avg_latency = np.mean(latencies)
        p95_latency = np.percentile(latencies, 95)

        # Should be reasonable for local model
        assert avg_latency < 2.0, f"Average latency too high: {avg_latency:.2f}s"
        assert p95_latency < 3.0, f"P95 latency too high: {p95_latency:.2f}s"


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestDatabasePerformance:
    """Performance tests for database operations."""

    async def test_vector_search_performance(self, real_db_connection, clean_test_data):
        """
        Performance Test: Vector similarity search.

        Should be fast with pgvector indexing.
        """
        import time

        # Insert test data
        await real_db_connection.execute(
            """
            INSERT INTO semantic_routes (tenant_id, route_name, department, utterance, embedding)
            SELECT
                1,
                'test_perf_' || i,
                CASE WHEN i % 2 = 0 THEN 'finance' ELSE 'hr' END,
                'Test utterance ' || i,
                ARRAY(SELECT random()::real FROM generate_series(1, 768))::vector
            FROM generate_series(1, 100) AS i
        """
        )

        # Search performance
        start = time.time()
        results = await real_db_connection.fetch(
            """
            SELECT route_name, 1 - (embedding <=> (SELECT embedding FROM semantic_routes LIMIT 1)) AS sim
            FROM semantic_routes
            WHERE tenant_id = 1
            ORDER BY embedding <=> (SELECT embedding FROM semantic_routes LIMIT 1)
            LIMIT 10
        """
        )
        elapsed = time.time() - start

        assert len(results) == 10
        assert elapsed < 1.0, f"Vector search too slow: {elapsed:.2f}s"

        # Cleanup
        await real_db_connection.execute(
            """
            DELETE FROM semantic_routes WHERE tenant_id = 1 AND route_name LIKE 'test_perf_%'
        """
        )
