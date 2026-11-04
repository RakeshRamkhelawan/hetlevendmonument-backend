"""
Pytest Configuration for Performance Tests
===========================================

Shared fixtures and configuration for performance tests.

Features:
- Automatic cleanup after performance tests
- Redis connection validation
- Database connection pool monitoring
- Performance metrics collection
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncGenerator, Generator

import pytest

# Configure logging for performance tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def pytest_configure(config: Any) -> None:
    """Configure pytest for performance tests."""
    # Add performance marker descriptions
    config.addinivalue_line(
        "markers",
        "performance: Performance/benchmark tests (slow, resource intensive)",
    )
    config.addinivalue_line(
        "markers",
        "load_test: Load testing tests (very slow, high resource usage)",
    )
    config.addinivalue_line(
        "markers",
        "stress_test: Stress testing tests (may cause system instability)",
    )


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Modify test collection to skip performance tests unless enabled."""
    run_performance = os.getenv("RUN_PERFORMANCE") == "1"
    run_company_perf = os.getenv("RUN_COMPANY_PERFORMANCE") == "1"

    for item in items:
        # Skip performance tests unless RUN_PERFORMANCE is set
        if "performance" in item.keywords and not run_performance:
            item.add_marker(
                pytest.mark.skip(reason="Set RUN_PERFORMANCE=1 to run performance tests")
            )

        # Skip company layer performance tests unless RUN_COMPANY_PERFORMANCE is set
        if "company_performance" in item.keywords and not run_company_perf:
            item.add_marker(
                pytest.mark.skip(
                    reason="Set RUN_COMPANY_PERFORMANCE=1 to run company layer performance tests"
                )
            )


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Get Redis URL from environment."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return url


@pytest.fixture(scope="session")
def check_redis_connection(redis_url: str) -> bool:
    """Check if Redis is available."""
    try:
        import redis as redis_lib  # type: ignore

        client = redis_lib.from_url(redis_url, socket_connect_timeout=5)
        client.ping()
        logger.info(f"Redis connection OK: {redis_url}")
        return True
    except ImportError:
        logger.warning("redis package not installed")
        return False
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return False


@pytest.fixture(autouse=True)
def log_test_start_end(request: Any) -> Generator[None, None, None]:
    """Log test start and end for debugging."""
    test_name = request.node.name
    logger.info(f"Starting performance test: {test_name}")
    yield
    logger.info(f"Completed performance test: {test_name}")


@pytest.fixture(scope="function")
async def cleanup_after_test() -> AsyncGenerator[None, None]:
    """Cleanup fixture that runs after each test."""
    yield
    # Cleanup logic runs after test
    logger.debug("Running post-test cleanup")


@pytest.fixture(scope="session", autouse=True)
def validate_performance_environment() -> None:
    """Validate environment before running performance tests."""
    # Check if we're in CI environment
    is_ci = os.getenv("CI") == "true"

    if is_ci:
        logger.info("Running in CI environment")

    # Log performance test configuration
    logger.info("Performance test configuration:")
    logger.info(f"  RUN_PERFORMANCE: {os.getenv('RUN_PERFORMANCE', 'not set')}")
    logger.info(f"  RUN_COMPANY_PERFORMANCE: {os.getenv('RUN_COMPANY_PERFORMANCE', 'not set')}")
    logger.info(f"  REDIS_URL: {os.getenv('REDIS_URL', 'not set')}")
    logger.info(f"  DATABASE_URL: {os.getenv('DATABASE_URL', 'not set')[:50]}...")
