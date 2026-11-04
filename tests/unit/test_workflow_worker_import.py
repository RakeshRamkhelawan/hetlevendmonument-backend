"""TDD tests for A2.7: workflow_worker.py lazy import."""

import os
import subprocess
import sys


def test_workflow_worker_imports_cleanly_without_db_url() -> None:
    """Module should import without crashing even without DATABASE_URL."""
    env = {
        **os.environ,
        "TESTING": "1",
        "DATABASE_URL": "",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
        "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import src.workers.workflow_worker"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"


def test_broker_and_engine_are_lazy() -> None:
    """Broker and engine should not be instantiated at import time."""
    env = {
        **os.environ,
        "TESTING": "1",
        "DATABASE_URL": "sqlite+aiosqlite:///test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
        "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
    }
    code = """
import sys
# Prevent __init__.py from loading and caching the module
sys.modules.pop("src.workers", None)
sys.modules.pop("src.workers.workflow_worker", None)

import src.workers.workflow_worker as ww

# Check that broker, engine, and session maker are not real instances
has_redis = "redis_broker" in ww.__dict__ and ww.__dict__["redis_broker"] is not None
has_engine = "engine" in ww.__dict__ and ww.__dict__["engine"] is not None
has_session = "async_session_maker" in ww.__dict__ and ww.__dict__["async_session_maker"] is not None

print(f"has_redis={has_redis} has_engine={has_engine} has_session={has_session}")
if has_redis or has_engine or has_session:
    sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Lazy check failed: {result.stdout} {result.stderr}"
