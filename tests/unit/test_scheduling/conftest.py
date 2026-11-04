"""Scheduling unit test fixtures.

Provides an autouse fixture that resets the module-level rate-limiter storage
before and after each test, preventing inter-test interference caused by the
shared in-memory counter.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_scheduling_limiter():
    """Reset the scheduling rate-limiter's in-memory storage around each test."""
    from src.core.scheduling.api.routes import limiter as _limiter

    storage = getattr(_limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
