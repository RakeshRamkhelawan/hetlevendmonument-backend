"""
Real Integration Test Configuration.

This module provides fixtures that connect to REAL external services.
No mocks, no placeholders - actual database queries and HTTP calls.
"""

import asyncio
import os
import socket
import time

import asyncpg
import pytest
import pytest_asyncio
import redis.asyncio as redis

# =============================================================================
# Service Availability Checks
# =============================================================================


def check_service(host: str, port: int, timeout: int = 2) -> bool:
    """Check if a service is available on given host:port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Check services
POSTGRES_AVAILABLE = check_service("localhost", 5435)  # Our mapped port
OLLAMA_AVAILABLE = check_service("localhost", 11434)
REDIS_AVAILABLE = check_service("localhost", 6385)  # Our mapped port

# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Configure pytest with integration markers."""
    config.addinivalue_line("markers", "integration: mark test as requiring external services")
    config.addinivalue_line("markers", "requires_postgres: mark test as requiring PostgreSQL")
    config.addinivalue_line("markers", "requires_ollama: mark test as requiring Ollama")
    config.addinivalue_line("markers", "requires_redis: mark test as requiring Redis")


# =============================================================================
# Real Service Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def postgres_available():
    """Check if PostgreSQL is available."""
    if not POSTGRES_AVAILABLE:
        pytest.skip("PostgreSQL not available on localhost:5435")
    return True


@pytest.fixture(scope="session")
def ollama_available():
    """Check if Ollama is available."""
    if not OLLAMA_AVAILABLE:
        pytest.skip("Ollama not available on localhost:11434")
    return True


@pytest.fixture(scope="session")
def redis_available():
    """Check if Redis is available."""
    if not REDIS_AVAILABLE:
        pytest.skip("Redis not available on localhost:6385")
    return True


@pytest_asyncio.fixture
async def real_db_connection(postgres_available):
    """
    REAL database connection to PostgreSQL with pgvector.

    This creates an actual connection to the database and runs real queries.
    """
    # Use connection parameters from .env or defaults
    conn = await asyncpg.connect(
        host="localhost", port=5435, user="postgres", password="postgres", database="sanskritisetu"
    )

    # Verify pgvector is installed
    try:
        await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    except Exception as e:
        await conn.close()
        pytest.skip(f"pgvector extension not installed: {e}")

    yield conn

    # Cleanup
    await conn.close()


@pytest_asyncio.fixture
async def real_redis_client(redis_available):
    """
    REAL Redis client for Pub/Sub tests.

    This connects to actual Redis and performs real operations.
    """
    client = redis.Redis(host="localhost", port=6385, decode_responses=True)

    # Verify connection
    try:
        await client.ping()
    except Exception as e:
        await client.close()
        pytest.skip(f"Redis connection failed: {e}")

    yield client

    # Cleanup
    await client.close()


@pytest_asyncio.fixture
async def real_ollama_embedder(ollama_available):
    """
    REAL Ollama embedder that makes actual HTTP calls.

    This generates real embeddings using nomic-embed-text model.
    """
    from src.core.semantic_router.embedders import OllamaEmbedder

    embedder = OllamaEmbedder(model="nomic-embed-text", base_url="http://localhost:11434")

    # Verify model is available
    if not await embedder.health_check():
        await embedder.close()
        pytest.skip("nomic-embed-text model not loaded in Ollama")

    yield embedder

    # Cleanup
    await embedder.close()


@pytest_asyncio.fixture
async def real_semantic_router(real_db_connection, real_ollama_embedder):
    """
    REAL semantic router with actual database and embedder.

    This is a fully functional router that:
    - Generates real embeddings via Ollama
    - Stores/retrieves routes from PostgreSQL
    - Performs real vector similarity search
    """
    from src.core.semantic_router.router import SanskritiSemanticRouter

    router = SanskritiSemanticRouter(
        tenant_id=1, embedder=real_ollama_embedder, similarity_threshold=0.7, top_k=5
    )

    await router.initialize()
    yield router

    await router.embedder.close()


@pytest_asyncio.fixture
async def clean_test_data(real_db_connection):
    """
    Clean up test data after tests.

    This fixture ensures tests don't pollute the database.
    """
    conn = real_db_connection

    # Clean up before test
    await conn.execute(
        """
        DELETE FROM semantic_routes
        WHERE tenant_id = 1
        AND route_name LIKE 'test_%'
    """
    )

    await conn.execute(
        """
        DELETE FROM routing_feedback
        WHERE tenant_id = 1
        AND task_text LIKE '%test%'
    """
    )

    yield

    # Clean up after test
    await conn.execute(
        """
        DELETE FROM semantic_routes
        WHERE tenant_id = 1
        AND route_name LIKE 'test_%'
    """
    )

    await conn.execute(
        """
        DELETE FROM routing_feedback
        WHERE tenant_id = 1
        AND task_text LIKE '%test%'
    """
    )


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def real_test_tasks():
    """Real test tasks for integration testing."""
    return {
        "finance": {
            "task": "Process quarterly financial reports",
            "description": "Review and approve Q4 2025 financial statements",
            "expected_department": "finance",
        },
        "hr": {
            "task": "Conduct performance reviews",
            "description": "Annual employee performance evaluation cycle",
            "expected_department": "hr",
        },
        "security": {
            "task": "Audit security vulnerabilities",
            "description": "Penetration testing and vulnerability assessment",
            "expected_department": "it_security",
        },
        "product": {
            "task": "Design new feature mockups",
            "description": "Create UX/UI designs for mobile app v2",
            "expected_department": "product_innovation",
        },
    }


@pytest.fixture
def real_workflow_events():
    """Real workflow events for event handler tests."""
    return [
        {
            "event_type": "workflow:started",
            "data": {
                "workflow_id": "wf_real_test_001",
                "workflow_type": "campaign",
                "tenant_id": 1,
            },
        },
        {
            "event_type": "task:created",
            "data": {
                "task_id": "task_real_001",
                "name": "Design campaign assets",
                "department": "sales_marketing",
            },
        },
    ]
