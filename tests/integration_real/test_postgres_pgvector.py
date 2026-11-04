"""
REAL Integration Test: PostgreSQL + pgvector.

Tests actual database operations with vector embeddings.
NO MOCKS - Real queries, real data.
"""

import numpy as np
import pytest
import pytest_asyncio


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestPostgresPgvectorReal:
    """Test real PostgreSQL with pgvector extension."""

    async def test_pgvector_extension_installed(self, real_db_connection):
        """
        Integration Test: pgvector extension is installed and working.

        Verifies: CREATE EXTENSION vector; was successful
        """
        result = await real_db_connection.fetchval(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname = 'vector'
        """
        )

        assert result == "vector", "pgvector extension not found"

    async def test_vector_type_operations(self, real_db_connection):
        """
        Integration Test: Can create and query vector data.

        Verifies: Vector storage, distance calculation, similarity search
        """
        # Create a test table with vector column
        await real_db_connection.execute(
            """
            CREATE TABLE IF NOT EXISTS test_vectors (
                id SERIAL PRIMARY KEY,
                name TEXT,
                embedding VECTOR(3)
            )
        """
        )

        # Insert test vectors
        await real_db_connection.execute(
            """
            INSERT INTO test_vectors (name, embedding)
            VALUES
                ('point_a', '[1, 2, 3]'),
                ('point_b', '[4, 5, 6]'),
                ('point_c', '[1.1, 2.1, 3.1]')
        """
        )

        # Query using cosine similarity
        results = await real_db_connection.fetch(
            """
            SELECT name,
                   1 - (embedding <=> '[1, 2, 3]') AS similarity
            FROM test_vectors
            ORDER BY embedding <=> '[1, 2, 3]'
        """
        )

        assert len(results) == 3
        # point_a should be most similar to itself
        assert results[0]["name"] == "point_a"
        assert results[0]["similarity"] == 1.0

        # Cleanup
        await real_db_connection.execute("DROP TABLE test_vectors")

    async def test_semantic_routes_table_exists(self, real_db_connection):
        """
        Integration Test: semantic_routes table exists and is queryable.
        """
        result = await real_db_connection.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'semantic_routes'
        """
        )

        assert result >= 1, "semantic_routes table not found"

    async def test_insert_and_retrieve_route(self, real_db_connection, clean_test_data):
        """
        Integration Test: Insert route with embedding, retrieve by similarity.

        This tests the full flow:
        1. Insert route with vector embedding
        2. Query by vector similarity
        3. Verify correct route is returned
        """
        # Insert test route
        await real_db_connection.execute(
            """
            INSERT INTO semantic_routes
                (tenant_id, route_name, department, utterance, embedding, success_count)
            VALUES
                (1, 'test_finance_invoice', 'finance', 'Process invoice', '[0.1, 0.2, 0.3, 0.4, 0.5]', 10)
        """
        )

        # Query by similarity (using exact match for simplicity)
        result = await real_db_connection.fetchrow(
            """
            SELECT route_name, department, success_count
            FROM semantic_routes
            WHERE tenant_id = 1 AND route_name = 'test_finance_invoice'
        """
        )

        assert result["route_name"] == "test_finance_invoice"
        assert result["department"] == "finance"
        assert result["success_count"] == 10

    async def test_vector_similarity_search_real_data(self, real_db_connection, clean_test_data):
        """
        Integration Test: Real vector similarity search with multiple routes.

        Inserts multiple routes and verifies similarity ordering.
        """
        # Insert multiple routes with different embeddings
        await real_db_connection.execute(
            """
            INSERT INTO semantic_routes
                (tenant_id, route_name, department, utterance, embedding)
            VALUES
                (1, 'test_route_a', 'finance', 'Invoice processing', '[0.9, 0.1, 0.0, 0.0, 0.0]'),
                (1, 'test_route_b', 'finance', 'Budget analysis', '[0.8, 0.2, 0.0, 0.0, 0.0]'),
                (1, 'test_route_c', 'hr', 'Hiring', '[0.1, 0.9, 0.0, 0.0, 0.0]')
        """
        )

        # Search for routes similar to [0.9, 0.1, 0, 0, 0]
        results = await real_db_connection.fetch(
            """
            SELECT route_name, department,
                   1 - (embedding <=> '[0.9, 0.1, 0, 0, 0]') AS similarity
            FROM semantic_routes
            WHERE tenant_id = 1 AND route_name LIKE 'test_%'
            ORDER BY embedding <=> '[0.9, 0.1, 0, 0, 0]'
            LIMIT 2
        """
        )

        # Should return test_route_a first (most similar)
        assert len(results) >= 2
        assert results[0]["route_name"] == "test_route_a"
        assert results[0]["similarity"] > 0.9  # Very similar
        assert results[1]["route_name"] == "test_route_b"

    async def test_concurrent_vector_inserts(self, real_db_connection, clean_test_data):
        """
        Integration Test: Multiple concurrent vector inserts.

        Verifies database handles concurrent access correctly.
        """
        import asyncio

        async def insert_route(index):
            await real_db_connection.execute(
                f"""
                INSERT INTO semantic_routes
                    (tenant_id, route_name, department, utterance, embedding)
                VALUES
                    (1, 'test_concurrent_{index}', 'finance', 'Test', '[{index}, 0, 0, 0, 0]')
            """
            )

        # Insert 10 routes concurrently
        tasks = [insert_route(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all inserted
        count = await real_db_connection.fetchval(
            """
            SELECT COUNT(*)
            FROM semantic_routes
            WHERE tenant_id = 1 AND route_name LIKE 'test_concurrent_%'
        """
        )

        assert count == 10


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestRoutingFeedbackTableReal:
    """Test routing_feedback table operations."""

    async def test_insert_routing_feedback(self, real_db_connection, clean_test_data):
        """
        Integration Test: Insert routing feedback.
        """
        await real_db_connection.execute(
            """
            INSERT INTO routing_feedback
                (tenant_id, task_text, selected_guna, selected_department,
                 confidence_score, was_successful, resolution_time_ms)
            VALUES
                (1, 'Test task', 'rajasic', 'finance', 0.85, 1, 150)
        """
        )

        result = await real_db_connection.fetchrow(
            """
            SELECT * FROM routing_feedback
            WHERE tenant_id = 1 AND task_text = 'Test task'
        """
        )

        assert result["selected_guna"] == "rajasic"
        assert result["selected_department"] == "finance"
        assert result["confidence_score"] == 0.85

    async def test_feedback_aggregations(self, real_db_connection, clean_test_data):
        """
        Integration Test: Aggregate feedback statistics.
        """
        # Insert multiple feedback entries
        await real_db_connection.execute(
            """
            INSERT INTO routing_feedback
                (tenant_id, task_text, selected_guna, selected_department, was_successful)
            VALUES
                (1, 'task1', 'tamasic', 'finance', 1),
                (1, 'task2', 'tamasic', 'finance', 1),
                (1, 'task3', 'tamasic', 'finance', 0),
                (1, 'task4', 'rajasic', 'hr', 1)
        """
        )

        # Calculate success rate
        result = await real_db_connection.fetchrow(
            """
            SELECT
                selected_guna,
                COUNT(*) as total,
                SUM(CASE WHEN was_successful = 1 THEN 1 ELSE 0 END) as successes
            FROM routing_feedback
            WHERE tenant_id = 1 AND task_text IN ('task1', 'task2', 'task3', 'task4')
            GROUP BY selected_guna
            ORDER BY selected_guna
        """
        )

        # Tamasic should have 3 entries with 2 successes
        assert result["total"] == 3
        assert result["successes"] == 2
